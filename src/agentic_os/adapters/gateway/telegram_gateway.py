"""Telegram Bot Gateway — submit missions and receive results via Telegram.

Connects to the Telegram Bot API using python-telegram-bot. When a user
sends a message to the bot, it creates a mission in the AgenticOS pipeline.
When the mission completes, the bot sends a notification back to the user.

Commands:
  /start    — Welcome + instructions
  /mission  — Create a new mission from the message text
  /status   — Show all active missions
  /result   — Get result of a specific mission
  Plain text — Treated as a new mission prompt
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("gateway.telegram")


@dataclass
class TelegramMessage:
    chat_id: int
    text: str
    username: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class TelegramGateway:
    """Telegram bot gateway for AgenticOS.

    Runs as an async background task. Listens for incoming messages and
    creates missions. Subscribes to mission/task events to send notifications back.
    """

    def __init__(
        self,
        bus: EventBus,
        bot_token: str = "",
        allowed_users: list[int] | None = None,
    ) -> None:
        self._bus = bus
        self._bot_token = bot_token
        self._allowed_users = set(allowed_users) if allowed_users else None
        self._bot: Any = None
        self._app: Any = None
        self._running = False
        self._bot_username: str = ""
        self._recent_messages: list[dict] = []
        self._chat_missions: dict[int, list[str]] = {}
        self._mission_chats: dict[str, int] = {}

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def bot_username(self) -> str:
        return f"@{self._bot_username}" if self._bot_username else ""

    async def start(self) -> None:
        """Start the Telegram bot.

        Raises RuntimeError if the bot cannot start (missing token,
        missing python-telegram-bot package, invalid token, network
        error reaching Telegram API). The caller (API endpoint) should
        catch this and return an HTTP error so the frontend can display
        the failure reason.
        """
        if not self._bot_token:
            raise RuntimeError("Bot token is required. Get one from @BotFather on Telegram.")

        try:
            from telegram import Bot
            from telegram.ext import (
                Application,
                CommandHandler,
                MessageHandler,
                filters,
            )
        except ImportError:
            raise RuntimeError(
                "python-telegram-bot is not installed. "
                "Run: pip install python-telegram-bot"
            )

        self._bot = Bot(token=self._bot_token)
        self._app = Application.builder().token(self._bot_token).build()

        # Get bot info — validates the token against Telegram API
        try:
            me = await self._bot.get_me()
            self._bot_username = me.username or ""
            log.info("telegram.connected", username=self._bot_username)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to connect to Telegram API. Check your bot token. "
                f"Error: {exc}"
            ) from exc

        # Register handlers
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("mission", self._on_mission_command))
        self._app.add_handler(CommandHandler("status", self._on_status))
        self._app.add_handler(CommandHandler("result", self._on_result))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text))

        # Subscribe to mission/task events for notifications
        await self._bus.subscribe(Topic.MISSION_COMPLETED.value, self._on_mission_completed)
        await self._bus.subscribe(Topic.MISSION_FAILED.value, self._on_mission_failed)
        await self._bus.subscribe("task.completed", self._on_task_completed)
        await self._bus.subscribe("task.failed", self._on_task_failed)

        await self._bus.publish(
            EventEnvelope(
                type="gateway.telegram.connected",
                source="telegram_gateway",
                topic="gateway.telegram.connected",
                payload={"username": self._bot_username},
            )
        )

        self._running = True

        # Start polling in background
        await self._app.initialize()
        await self._app.start()
        if self._app.updater:
            await self._app.updater.start_polling(drop_pending_updates=True)
        log.info("telegram.polling_started")

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self._app:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception:
                pass
        self._running = False
        await self._bus.publish(
            EventEnvelope(
                type="gateway.telegram.disconnected",
                source="telegram_gateway",
                topic="gateway.telegram.disconnected",
                payload={},
            )
        )
        log.info("telegram.disconnected")

    async def send_message(self, chat_id: int, text: str) -> bool:
        """Send a message to a Telegram chat."""
        if not self._bot:
            return False
        try:
            await self._bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            self._recent_messages.append(
                {
                    "chat_id": chat_id,
                    "text": text,
                    "direction": "outgoing",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            await self._bus.publish(
                EventEnvelope(
                    type="gateway.telegram.message_sent",
                    source="telegram_gateway",
                    topic="gateway.telegram.message_sent",
                    payload={"chat_id": chat_id, "text": text},
                )
            )
            return True
        except Exception as exc:
            log.error("telegram.send_failed", chat_id=chat_id, error=str(exc))
            return False

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "username": self.bot_username,
            "recent_messages": self._recent_messages[-20:],
            "allowed_users": list(self._allowed_users) if self._allowed_users else None,
        }

    def get_recent_chats(self) -> list[dict]:
        seen: dict[int, dict] = {}
        for msg in self._recent_messages:
            cid = msg["chat_id"]
            if cid not in seen:
                seen[cid] = {
                    "chat_id": cid,
                    "last_message": msg["text"][:100],
                    "timestamp": msg["timestamp"],
                }
        return list(seen.values())[-20:]

    def _check_user(self, update: Any) -> bool:
        if self._allowed_users is None:
            return True
        user_id = update.effective_user.id if update.effective_user else 0
        return user_id in self._allowed_users

    async def _on_start(self, update: Any, context: Any) -> None:
        if not self._check_user(update):
            return
        chat_id = update.effective_chat.id
        welcome = (
            "🤖 <b>AgenticOS Bot</b>\n\n"
            "Send me a task and I'll dispatch it to AI agents!\n\n"
            "<b>Commands:</b>\n"
            "/mission &lt;prompt&gt; — Create a new mission\n"
            "/status — Show active missions\n"
            "/result &lt;mission_id&gt; — Get mission result\n\n"
            "Or just send any text — it will be treated as a mission prompt."
        )
        await self.send_message(chat_id, welcome)

    async def _on_mission_command(self, update: Any, context: Any) -> None:
        if not self._check_user(update):
            return
        chat_id = update.effective_chat.id
        text = " ".join(context.args) if context.args else ""
        if not text:
            await self.send_message(chat_id, "Usage: /mission <your prompt here>")
            return
        await self._create_mission_from_message(chat_id, text, update.effective_user.username or "")

    async def _on_status(self, update: Any, context: Any) -> None:
        if not self._check_user(update):
            return
        chat_id = update.effective_chat.id
        mission_ids = self._chat_missions.get(chat_id, [])
        if not mission_ids:
            await self.send_message(chat_id, "No missions yet. Send a message to create one!")
            return
        lines = [f"📋 <b>{len(mission_ids)} Missions:</b>"]
        for mid in mission_ids[-10:]:
            lines.append(f"• <code>{mid[:8]}</code>")
        await self.send_message(chat_id, "\n".join(lines))

    async def _on_result(self, update: Any, context: Any) -> None:
        if not self._check_user(update):
            return
        chat_id = update.effective_chat.id
        mission_id = " ".join(context.args) if context.args else ""
        if not mission_id:
            await self.send_message(chat_id, "Usage: /result <mission_id>")
            return
        await self.send_message(
            chat_id, f"Use Mission Control to view full results for mission {mission_id[:8]}"
        )

    async def _on_text(self, update: Any, context: Any) -> None:
        if not self._check_user(update):
            return
        chat_id = update.effective_chat.id
        text = update.message.text
        username = update.effective_user.username or ""
        await self._create_mission_from_message(chat_id, text, username)

    async def _create_mission_from_message(self, chat_id: int, text: str, username: str) -> None:
        """Create a mission from an incoming message."""
        self._recent_messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "username": username,
                "direction": "incoming",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        await self._bus.publish(
            EventEnvelope(
                type="gateway.telegram.message_received",
                source="telegram_gateway",
                topic="gateway.telegram.message_received",
                payload={"chat_id": chat_id, "text": text, "username": username},
            )
        )
        await self.send_message(chat_id, f"🚀 Mission started: {text[:60]}")

    def register_mission(self, chat_id: int, mission_id: str) -> None:
        """Track which chat_id a mission belongs to (for sending results back)."""
        self._chat_missions.setdefault(chat_id, []).append(mission_id)
        self._mission_chats[mission_id] = chat_id

    async def _on_mission_completed(self, event: EventEnvelope) -> None:
        mission_id = event.payload.get("id", "")
        chat_id = self._mission_chats.get(mission_id)
        if chat_id:
            await self.send_message(
                chat_id, f"🎉 Mission completed: {event.payload.get('title', '')[:60]}"
            )

    async def _on_mission_failed(self, event: EventEnvelope) -> None:
        mission_id = event.payload.get("id", "")
        chat_id = self._mission_chats.get(mission_id)
        if chat_id:
            await self.send_message(
                chat_id, f"❌ Mission failed: {event.payload.get('title', '')[:60]}"
            )

    async def _on_task_completed(self, event: EventEnvelope) -> None:
        mission_id = event.payload.get("mission_id", "")
        chat_id = self._mission_chats.get(mission_id)
        if chat_id:
            title = event.payload.get("title", event.payload.get("task_id", ""))[:40]
            result = event.payload.get("result", "")[:200]
            await self.send_message(chat_id, f"✅ Task completed: {title}\nResult: {result}")

    async def _on_task_failed(self, event: EventEnvelope) -> None:
        mission_id = event.payload.get("mission_id", "")
        chat_id = self._mission_chats.get(mission_id)
        if chat_id:
            title = event.payload.get("title", event.payload.get("task_id", ""))[:40]
            error = event.payload.get("error", "")[:200]
            await self.send_message(chat_id, f"❌ Task failed: {title}\nError: {error}")


__all__ = ["TelegramGateway", "TelegramMessage"]
