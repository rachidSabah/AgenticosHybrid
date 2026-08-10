"""Telegram Bot Gateway — submit missions and receive results via Telegram.

Connects to the Telegram Bot API using python-telegram-bot.  When a user
sends a message to the bot, it routes the prompt through the shared
:class:`RemotePromptService`, which creates a REAL mission in the AgenticOS
pipeline — the same pipeline the browser Prompt Center uses.  When the
mission (or a task) makes progress, the bot sends notifications back to the
originating chat.

Transport-only responsibilities live here: polling, chat identity, reply
formatting.  Mission semantics (authorization, rate limiting, idempotency,
audit, validation) live in ``RemotePromptService``.

Commands:
  /start       — Welcome + instructions
  /help        — Command list
  /mission     — Create a new mission from the message text
  /prompt      — Alias for /mission
  /status      — Mission + gateway summary
  /missions    — List your recent missions
  /result      — Detail of a specific mission
  /agents      — List live agents
  /cancel      — Cancel a mission you created
  /stop        — Alias for /cancel
  /retry       — Re-run a failed mission as a new mission
  Plain text   — Treated as a new mission prompt
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentic_os.adapters.gateway.remote_prompt import (
    CHANNEL_TELEGRAM,
    RemoteIdentity,
    RemotePromptService,
)
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("gateway.telegram")

# Topics subscribed for progress streaming back to the originating chat.
_PROGRESS_TOPICS = (
    "mission.started",
    "task.dispatched",
    "task.started",
    "task.completed",
    "task.failed",
)


@dataclass
class TelegramMessage:
    chat_id: int
    text: str
    username: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class TelegramGateway:
    """Telegram bot gateway for AgenticOS.

    Runs as an async background task.  Listens for incoming messages and
    creates real missions via the shared ``RemotePromptService``.  Subscribes
    to mission/task events to send progress + results back to the chat.
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
        self._remote: RemotePromptService | None = None
        self._bot: Any = None
        self._app: Any = None
        self._running = False
        self._bot_username: str = ""
        self._connected_at: str = ""
        self._recent_messages: list[dict] = []
        self._chat_missions: dict[int, list[str]] = {}
        self._mission_chats: dict[str, int] = {}

    # ── configuration accessors (encapsulation) ──────────────────────────────

    def set_remote_service(self, remote: RemotePromptService) -> None:
        """Inject the shared remote prompt service (called by app wiring)."""
        self._remote = remote

    def set_bot_token(self, token: str) -> None:
        self._bot_token = (token or "").strip()

    def set_allowed_users(self, users: list[int] | None) -> None:
        self._allowed_users = set(int(u) for u in users) if users else None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def bot_username(self) -> str:
        return f"@{self._bot_username}" if self._bot_username else ""

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the Telegram bot.

        Raises RuntimeError if the bot cannot start (missing token, missing
        python-telegram-bot package, invalid token, network error reaching the
        Telegram API).  The caller (API endpoint) catches this and returns an
        HTTP error so the frontend can display the failure reason.
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
                "python-telegram-bot is not installed. Run: pip install python-telegram-bot"
            ) from None

        self._bot = Bot(token=self._bot_token)
        self._app = Application.builder().token(self._bot_token).build()

        # Get bot info — validates the token against the Telegram API
        try:
            me = await self._bot.get_me()
            self._bot_username = me.username or ""
            log.info("telegram.connected", username=self._bot_username)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to connect to Telegram API. Check your bot token. Error: {exc}"
            ) from exc

        # Register command + text handlers
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("help", self._on_help))
        self._app.add_handler(CommandHandler("mission", self._on_mission_command))
        self._app.add_handler(CommandHandler("prompt", self._on_mission_command))
        self._app.add_handler(CommandHandler("status", self._on_status))
        self._app.add_handler(CommandHandler("missions", self._on_missions))
        self._app.add_handler(CommandHandler("result", self._on_result))
        self._app.add_handler(CommandHandler("agents", self._on_agents))
        self._app.add_handler(CommandHandler("cancel", self._on_cancel))
        self._app.add_handler(CommandHandler("stop", self._on_cancel))
        self._app.add_handler(CommandHandler("retry", self._on_retry))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text))

        # Subscribe to mission/task events for progress + result streaming
        await self._bus.subscribe(Topic.MISSION_COMPLETED.value, self._on_mission_completed)
        await self._bus.subscribe(Topic.MISSION_FAILED.value, self._on_mission_failed)
        for topic in _PROGRESS_TOPICS:
            await self._bus.subscribe(topic, self._on_progress_event)

        await self._bus.publish(
            EventEnvelope(
                type="gateway.telegram.connected",
                source="telegram_gateway",
                topic="gateway.telegram.connected",
                payload={"username": self._bot_username},
            )
        )

        self._running = True
        self._connected_at = datetime.now(UTC).isoformat()

        # Start polling in the background
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
        self._connected_at = ""
        await self._bus.publish(
            EventEnvelope(
                type="gateway.telegram.disconnected",
                source="telegram_gateway",
                topic="gateway.telegram.disconnected",
                payload={},
            )
        )
        log.info("telegram.disconnected")

    # ── send ─────────────────────────────────────────────────────────────────

    async def send_message(self, chat_id: int, text: str) -> bool:
        """Send a plain-text message to a Telegram chat (always HTML-safe)."""
        if not self._bot:
            return False
        try:
            await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                disable_web_page_preview=True,
            )
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

    # ── status / introspection ───────────────────────────────────────────────

    def get_status(self) -> dict:
        mission_count = len(self._chat_missions)
        return {
            "running": self._running,
            "username": self.bot_username,
            "connected_at": self._connected_at,
            "recent_messages": self._recent_messages[-20:],
            "allowed_users": list(self._allowed_users) if self._allowed_users else None,
            "mission_count": mission_count,
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

    # ── authorization ────────────────────────────────────────────────────────

    def _check_user(self, update: Any) -> bool:
        """True if the effective user may interact with the bot."""
        if self._allowed_users is None:
            return True
        user_id = update.effective_user.id if update.effective_user else 0
        return user_id in self._allowed_users

    async def _reject_unauthorized(self, update: Any) -> None:
        """Audit + silence interactions from non-allow-listed users."""
        user_id = update.effective_user.id if update.effective_user else 0
        await self._bus.publish(
            EventEnvelope(
                type="audit.event",
                source="telegram_gateway",
                topic=Topic.AUDIT.value,
                payload={
                    "timestamp": datetime.now(UTC).isoformat(),
                    "principal": str(user_id),
                    "channel": CHANNEL_TELEGRAM,
                    "action": "telegram.access",
                    "outcome": "deny",
                    "target": "",
                    "meta": {"reason": "not_allowlisted"},
                },
            )
        )

    # ── identity helpers ─────────────────────────────────────────────────────

    def _identity(self, update: Any) -> RemoteIdentity:
        user = update.effective_user
        return RemoteIdentity(
            channel=CHANNEL_TELEGRAM,
            external_account_id=str(user.id) if user else "",
            display_name=(user.username or user.first_name or "") if user else "",
        )

    def _record_incoming(self, chat_id: int, text: str, username: str) -> None:
        self._recent_messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "username": username,
                "direction": "incoming",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    # ── command handlers ─────────────────────────────────────────────────────

    async def _on_start(self, update: Any, context: Any) -> None:
        if not self._check_user(update):
            await self._reject_unauthorized(update)
            return
        chat_id = update.effective_chat.id
        welcome = (
            "🤖 AgenticOS — Mission Control via Telegram\n\n"
            "Send me a task and I'll dispatch it to the real AI agent swarm.\n\n"
            "Commands:\n"
            "/mission <prompt> — Create a mission\n"
            "/status — Mission + gateway summary\n"
            "/missions — List your missions\n"
            "/result <id> — Mission detail\n"
            "/agents — List live agents\n"
            "/cancel <id> — Cancel a mission\n"
            "/help — Full command list\n\n"
            "Or just send any text — it becomes a mission prompt."
        )
        await self.send_message(chat_id, welcome)

    async def _on_help(self, update: Any, context: Any) -> None:
        if not self._check_user(update):
            await self._reject_unauthorized(update)
            return
        chat_id = update.effective_chat.id
        help_text = (
            "📖 AgenticOS Bot Help\n\n"
            "/mission <prompt> — Create and start a mission\n"
            "/prompt <prompt> — Alias of /mission\n"
            "/status — Active missions + gateway state\n"
            "/missions — List your recent missions\n"
            "/result <mission_id> — Full detail of one mission\n"
            "/agents — List agents available for dispatch\n"
            "/cancel <mission_id> — Cancel a mission you own\n"
            "/stop <mission_id> — Alias of /cancel\n"
            "/retry <mission_id> — Re-run a failed mission as a new mission\n\n"
            "Plain text messages are treated as mission prompts."
        )
        await self.send_message(chat_id, help_text)

    async def _on_mission_command(self, update: Any, context: Any) -> None:
        if not self._check_user(update):
            await self._reject_unauthorized(update)
            return
        chat_id = update.effective_chat.id
        text = " ".join(context.args) if context.args else ""
        if not text:
            await self.send_message(chat_id, "Usage: /mission <your prompt here>")
            return
        await self._submit_prompt(update, chat_id, text, message_id="")

    async def _on_status(self, update: Any, context: Any) -> None:
        if not self._check_user(update):
            await self._reject_unauthorized(update)
            return
        chat_id = update.effective_chat.id
        mission_ids = self._chat_missions.get(chat_id, [])
        lines = [f"📋 Telegram gateway: {'online' if self._running else 'offline'}"]
        if self.bot_username:
            lines.append(f"Bot: {self.bot_username}")
        if not mission_ids:
            lines.append("No missions from this chat yet. Send a message to create one!")
        else:
            lines.append(f"You have {len(mission_ids)} mission(s):")
            for mid in mission_ids[-10:]:
                m = self._remote.get_mission(mid) if self._remote else None
                status = m.get("status", "") if m else "?"
                title = (m.get("title", "") or "")[:40] if m else ""
                lines.append(f"• {mid[:8]} [{status}] {title}")
        await self.send_message(chat_id, "\n".join(lines))

    async def _on_missions(self, update: Any, context: Any) -> None:
        if not self._check_user(update):
            await self._reject_unauthorized(update)
            return
        chat_id = update.effective_chat.id
        if not self._remote:
            await self.send_message(chat_id, "Remote prompt service is not available yet.")
            return
        missions = self._remote.list_missions()
        mine = [
            m
            for m in missions
            if self._chat_missions.get(chat_id, []) and m["id"] in self._chat_missions[chat_id]
        ]
        source = mine if mine else missions
        if not source:
            await self.send_message(chat_id, "No missions yet. Send a message to create one!")
            return
        lines = [f"📋 {len(source)} mission(s):"]
        for m in source[:10]:
            lines.append(
                f"• {m['id'][:8]} [{m.get('status', '')}] "
                f"({m.get('channel', 'WEB')}) {(m.get('title', '') or '')[:40]}"
            )
        await self.send_message(chat_id, "\n".join(lines))

    async def _on_result(self, update: Any, context: Any) -> None:
        if not self._check_user(update):
            await self._reject_unauthorized(update)
            return
        chat_id = update.effective_chat.id
        mission_id = " ".join(context.args) if context.args else ""
        if not mission_id:
            await self.send_message(chat_id, "Usage: /result <mission_id>")
            return
        if not self._remote:
            await self.send_message(chat_id, "Remote prompt service is not available yet.")
            return
        m = self._remote.get_mission(mission_id)
        if not m:
            await self.send_message(chat_id, f"Mission {mission_id[:12]} not found.")
            return
        plan = m.get("plan") or {}
        tasks = plan.get("tasks", [])
        done = sum(1 for t in tasks if t.get("status") == "completed")
        lines = [
            f"📦 Mission {m['id']}",
            f"Status: {m.get('status', '')}",
            f"Channel: {m.get('channel', 'WEB')}",
            f"Title: {(m.get('title', '') or '')[:80]}",
            f"Tasks: {done}/{len(tasks)} completed",
        ]
        prompt = (m.get("prompt", "") or "").strip()
        if prompt:
            lines.append(f"Prompt: {prompt[:200]}")
        await self.send_message(chat_id, "\n".join(lines))

    async def _on_agents(self, update: Any, context: Any) -> None:
        if not self._check_user(update):
            await self._reject_unauthorized(update)
            return
        chat_id = update.effective_chat.id
        if not self._remote:
            await self.send_message(chat_id, "Remote prompt service is not available yet.")
            return
        agents = await self._remote.list_agents()
        if not agents:
            await self.send_message(chat_id, "No agents registered yet.")
            return
        lines = ["🤖 Live agents:"]
        for a in agents[:20]:
            lines.append(
                f"• {a.get('id', a.get('name', '?'))} [{a.get('status', '?')}] "
                f"({(a.get('capabilities') or [])[:3]})"
            )
        await self.send_message(chat_id, "\n".join(lines))

    async def _on_cancel(self, update: Any, context: Any) -> None:
        if not self._check_user(update):
            await self._reject_unauthorized(update)
            return
        chat_id = update.effective_chat.id
        mission_id = " ".join(context.args) if context.args else ""
        if not mission_id:
            await self.send_message(chat_id, "Usage: /cancel <mission_id>")
            return
        if not self._remote:
            await self.send_message(chat_id, "Remote prompt service is not available yet.")
            return
        try:
            result = await self._remote.cancel(mission_id, self._identity(update))
        except Exception as exc:
            await self.send_message(chat_id, f"⚠️ Could not cancel: {getattr(exc, 'message', exc)}")
            return
        await self.send_message(
            chat_id, f"🛑 Mission {mission_id[:12]} cancelled (status: {result.get('status', '')})."
        )

    async def _on_retry(self, update: Any, context: Any) -> None:
        if not self._check_user(update):
            await self._reject_unauthorized(update)
            return
        chat_id = update.effective_chat.id
        mission_id = " ".join(context.args) if context.args else ""
        if not mission_id:
            await self.send_message(chat_id, "Usage: /retry <mission_id>")
            return
        if not self._remote:
            await self.send_message(chat_id, "Remote prompt service is not available yet.")
            return
        original = self._remote.get_mission(mission_id)
        if not original:
            await self.send_message(chat_id, f"Mission {mission_id[:12]} not found.")
            return
        prompt = original.get("prompt", "") or original.get("description", "")
        if not prompt:
            await self.send_message(chat_id, "Original mission has no prompt to retry.")
            return
        await self._submit_prompt(update, chat_id, prompt, message_id=f"retry:{mission_id}")

    async def _on_text(self, update: Any, context: Any) -> None:
        if not self._check_user(update):
            await self._reject_unauthorized(update)
            return
        chat_id = update.effective_chat.id
        text = update.message.text
        username = update.effective_user.username or ""
        message_id = ""
        if update.effective_message is not None and update.effective_message.message_id is not None:
            user_id = update.effective_user.id if update.effective_user else 0
            message_id = f"{user_id}:{update.effective_message.message_id}"
        await self._submit_prompt(update, chat_id, text, username, message_id)

    # ── mission submission (the core path) ───────────────────────────────────

    async def _submit_prompt(
        self,
        update: Any,
        chat_id: int,
        text: str,
        username: str = "",
        message_id: str = "",
    ) -> None:
        """Route a remote prompt into the shared mission pipeline."""
        self._record_incoming(chat_id, text, username)
        if not self._remote:
            await self.send_message(chat_id, "Remote prompt service is not available yet.")
            return
        identity = self._identity(update)
        try:
            mission = await self._remote.submit(
                prompt=text,
                identity=identity,
                message_id=message_id,
            )
        except Exception as exc:
            await self.send_message(
                chat_id,
                f"⚠️ {getattr(exc, 'message', 'Mission could not be created.')}",
            )
            return
        mid = mission.get("id", "")
        self.register_mission(chat_id, mid)
        title = (mission.get("title", "") or "")[:60]
        await self.send_message(
            chat_id,
            f"🚀 Mission {mid[:8]} created and dispatched: {title}\n"
            f"Progress will be streamed here. Full results: Mission Control → Mission {mid}.",
        )

    def register_mission(self, chat_id: int, mission_id: str) -> None:
        """Track which chat a mission belongs to (for sending results back)."""
        self._chat_missions.setdefault(chat_id, []).append(mission_id)
        self._mission_chats[mission_id] = chat_id

    # ── event callbacks (progress + results) ─────────────────────────────────

    async def _on_mission_completed(self, event: EventEnvelope) -> None:
        mission_id = event.payload.get("id", "")
        chat_id = self._mission_chats.get(mission_id)
        if chat_id:
            await self.send_message(
                chat_id,
                f"🎉 Mission {mission_id[:8]} completed: "
                f"{(event.payload.get('title', '') or '')[:60]}",
            )

    async def _on_mission_failed(self, event: EventEnvelope) -> None:
        mission_id = event.payload.get("id", "")
        chat_id = self._mission_chats.get(mission_id)
        if chat_id:
            await self.send_message(
                chat_id,
                f"❌ Mission {mission_id[:8]} failed: "
                f"{(event.payload.get('title', '') or '')[:60]}",
            )

    async def _on_progress_event(self, event: EventEnvelope) -> None:
        """Stream task-level progress to the originating chat."""
        mission_id = event.payload.get("mission_id", "")
        chat_id = self._mission_chats.get(mission_id)
        if not chat_id:
            return
        etype = event.type
        title = (event.payload.get("title", "") or "")[:50]
        if etype == "mission.started":
            await self.send_message(
                chat_id, f"🔄 Mission {mission_id[:8]} executing — progress below."
            )
        elif etype == "task.dispatched":
            agent = event.payload.get("agent", "") or ""
            await self.send_message(
                chat_id,
                f"🤖 Task '{title}' → agent {agent}".strip(),
            )
        elif etype == "task.started":
            await self.send_message(chat_id, f"▶️ Task '{title}' started")
        elif etype == "task.completed":
            await self.send_message(chat_id, f"✅ Task '{title}' completed")
        elif etype == "task.failed":
            error = (event.payload.get("error", "") or "")[:160]
            await self.send_message(chat_id, f"❌ Task '{title}' failed: {error}")

    async def _on_task_completed(self, event: EventEnvelope) -> None:
        """Backward-compatible handler (unused; kept for API stability)."""
        mission_id = event.payload.get("mission_id", "")
        chat_id = self._mission_chats.get(mission_id)
        if chat_id:
            title = event.payload.get("title", event.payload.get("task_id", ""))[:40]
            await self.send_message(chat_id, f"✅ Task completed: {title}")

    async def _on_task_failed(self, event: EventEnvelope) -> None:
        mission_id = event.payload.get("mission_id", "")
        chat_id = self._mission_chats.get(mission_id)
        if chat_id:
            title = event.payload.get("title", event.payload.get("task_id", ""))[:40]
            error = event.payload.get("error", "")[:200]
            await self.send_message(chat_id, f"❌ Task failed: {title}\nError: {error}")


__all__ = ["TelegramGateway", "TelegramMessage"]
