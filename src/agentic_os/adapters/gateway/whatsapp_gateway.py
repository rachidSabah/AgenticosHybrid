"""WhatsApp Gateway — submit missions and receive results via WhatsApp.

Uses @whiskeysockets/baileys (Node.js) via a standalone bridge script at
E:/Agenticos/wa_bridge.js to connect to WhatsApp Web.  Scans a real QR code
for authentication, then listens for incoming messages and routes them through
the shared :class:`RemotePromptService` — the same mission pipeline the
browser Prompt Center uses.

Architecture
------------
* The bridge script (wa_bridge.js) lives at a fixed absolute path so Python
  never has to write it at runtime — eliminating the cwd/path-resolution bug.
* Python spawns ``node wa_bridge.js`` with cwd=project_root using
  ``subprocess.Popen`` (not ``asyncio.create_subprocess_exec``) so it works
  under both ProactorEventLoop and SelectorEventLoop on Windows.
* Events flow over stdout as JSON lines; commands (send) arrive on stdin.
* A background thread reads stdout and dispatches events onto the asyncio loop
  via ``loop.call_soon_threadsafe``.

Commands (WhatsApp text messages):
  /start, /help, /mission <prompt>, /status, /missions, /result <id>,
  /agents, /cancel <id>, /stop <id>, /retry <id>
  Any non-command text is treated as a mission prompt.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from agentic_os.adapters.gateway.remote_prompt import (
    CHANNEL_WHATSAPP,
    RemoteIdentity,
    RemotePromptService,
)
from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("gateway.whatsapp")

# ── constants ────────────────────────────────────────────────────────────────

# Absolute path to the pre-written bridge script — never computed at runtime.
# This avoids the cwd / __file__ resolution issue inside ``uv run``.
_PROJECT_ROOT = Path("E:/Agenticos")
_BRIDGE_SCRIPT_PATH = _PROJECT_ROOT / "wa_bridge.js"

# Topics subscribed for progress streaming back to the originating chat.
_PROGRESS_TOPICS = (
    "mission.started",
    "task.dispatched",
    "task.started",
    "task.completed",
    "task.failed",
)


@dataclass
class WhatsAppMessage:
    from_number: str
    text: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ── gateway ──────────────────────────────────────────────────────────────────


class WhatsAppGateway:
    """WhatsApp gateway using @whiskeysockets/baileys via Node.js subprocess.

    The Node.js bridge connects to WhatsApp Web and communicates via
    stdout/stdin JSON messages.

    Uses ``subprocess.Popen`` (not ``asyncio.create_subprocess_exec``) so it
    works under both ProactorEventLoop and WindowsSelectorEventLoopPolicy on
    Windows.
    """

    def __init__(
        self,
        bus: EventBus,
        session_path: str = "",
        allowed_numbers: list[str] | None = None,
    ) -> None:
        self._bus = bus
        self._session_path = session_path or os.path.expanduser("~/.agentic_os/whatsapp_session")
        self._allowed_numbers: set[str] | None = set(allowed_numbers) if allowed_numbers else None
        self._remote: RemotePromptService | None = None
        self._process: subprocess.Popen | None = None
        self._running = False
        self._qr_code: str = ""
        self._connection_status: str = "disconnected"
        self._connected_at: str = ""
        self._recent_messages: list[dict] = []
        self._chat_missions: dict[str, list[str]] = {}
        self._mission_chats: dict[str, str] = {}
        self._reader_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ── configuration accessors (encapsulation) ──────────────────────────────

    def set_remote_service(self, remote: RemotePromptService) -> None:
        """Inject the shared remote prompt service (called by app wiring)."""
        self._remote = remote

    def set_session_path(self, session_path: str) -> None:
        if session_path:
            self._session_path = session_path

    def set_allowed_numbers(self, numbers: list[str] | None) -> None:
        self._allowed_numbers = (
            {self._normalize_number(n) for n in numbers if self._normalize_number(n)}
            if numbers
            else None
        )

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def qr_code(self) -> str:
        return self._qr_code

    @property
    def connection_status(self) -> str:
        return self._connection_status

    # ── start / stop ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the WhatsApp gateway.

        Raises
        ------
        RuntimeError
            If Node.js is not on PATH, the bridge script is missing, or the
            process exits immediately.  The API layer should catch this and
            return HTTP 502 to the frontend.
        """
        # Validate the bridge script exists
        bridge_path = _BRIDGE_SCRIPT_PATH
        if not bridge_path.exists():
            raise RuntimeError(
                f"WhatsApp bridge script not found at {bridge_path}. "
                "Please ensure wa_bridge.js exists in the project root."
            )

        # Ensure session directory exists.  Filesystem errors here must map to
        # the same 502 contract as other startup failures, not leak as 500.
        try:
            os.makedirs(self._session_path, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(
                f"Failed to create WhatsApp session directory {self._session_path}: {exc}"
            ) from exc

        log.info(
            "whatsapp.starting",
            bridge=str(bridge_path),
            session=self._session_path,
            cwd=str(_PROJECT_ROOT),
        )

        # Build environment: propagate current env + session path
        env = {
            **os.environ,
            "WA_SESSION_PATH": self._session_path,
        }

        # Use subprocess.Popen (not asyncio.create_subprocess_exec) so this
        # works under WindowsSelectorEventLoopPolicy which doesn't support
        # asyncio subprocesses on Windows.
        try:
            self._process = subprocess.Popen(
                ["node", str(bridge_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=str(_PROJECT_ROOT),
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Node.js is not installed or not on PATH. "
                "WhatsApp gateway requires Node.js (v18+) to run the bridge script. "
                "Install from https://nodejs.org/"
            ) from None
        except Exception as exc:
            raise RuntimeError(f"Failed to spawn WhatsApp bridge: {exc}") from exc

        # Give the process 1 s to start up or fail fast
        await asyncio.sleep(1.0)
        if self._process.returncode is not None:
            stderr_snippet = ""
            stderr = self._process.stderr
            if stderr is not None:
                try:
                    stderr_snippet = (stderr.read(500) or "").strip()
                except Exception:
                    pass
            raise RuntimeError(
                f"WhatsApp bridge exited immediately (code {self._process.returncode})"
                + (f": {stderr_snippet}" if stderr_snippet else "")
            )

        self._running = True
        self._connection_status = "connecting"

        # Capture the running event loop so the reader thread can schedule
        # coroutines back onto it safely.
        self._loop = asyncio.get_running_loop()

        # Start background threads to drain stdout and stderr
        self._reader_thread = threading.Thread(
            target=self._stdout_reader,
            args=(self._process.stdout,),
            daemon=True,
            name="wa_bridge_stdout",
        )
        self._reader_thread.start()

        stderr_thread = threading.Thread(
            target=self._stderr_drainer,
            args=(self._process.stderr,),
            daemon=True,
            name="wa_bridge_stderr",
        )
        stderr_thread.start()

        # Monitor the process in background
        asyncio.create_task(self._monitor_process(), name="wa_bridge_monitor")

        # Subscribe to mission/task events for progress + result streaming
        await self._bus.subscribe(Topic.MISSION_COMPLETED.value, self._on_mission_completed)
        await self._bus.subscribe(Topic.MISSION_FAILED.value, self._on_mission_failed)
        for topic in _PROGRESS_TOPICS:
            await self._bus.subscribe(topic, self._on_progress_event)

        log.info("whatsapp.gateway_started")

    # ── stdout / stderr readers (run in daemon threads) ───────────────────────

    def _stdout_reader(self, stdout: IO[str]) -> None:
        """Read JSON lines from the bridge's stdout and dispatch to the loop."""
        try:
            for line in stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    log.debug("whatsapp.bridge_stdout_non_json", line=line[:200])
                    continue
                # Schedule the handler back on the asyncio event loop
                if self._loop and not self._loop.is_closed():
                    self._loop.call_soon_threadsafe(
                        lambda e=event: asyncio.ensure_future(self._handle_bridge_event(e))
                    )
        except Exception as exc:
            log.debug("whatsapp.stdout_reader_exit", reason=str(exc))

    def _stderr_drainer(self, stderr: IO[str]) -> None:
        """Drain stderr so the bridge subprocess never blocks on a full pipe."""
        try:
            for line in stderr:
                line = line.strip()
                if line:
                    log.debug("whatsapp.bridge_stderr", line=line[:300])
        except Exception:
            pass

    async def _handle_bridge_event(self, event: dict) -> None:
        """Process a parsed JSON event from the bridge."""
        etype = event.get("type", "")

        if etype == "qr":
            self._qr_code = event.get("qr", "")
            log.info("whatsapp.qr_received")
            # The QR string itself is a pairing secret — never put it on the
            # bus/WS feed. Clients poll /api/gateway/whatsapp/qr for the live
            # render instead. Only the availability bit is broadcast.
            await self._bus.publish(
                EventEnvelope(
                    type="gateway.whatsapp.qr",
                    source="whatsapp_gateway",
                    topic="gateway.whatsapp.qr",
                    payload={"has_qr": True},
                )
            )

        elif etype == "connected":
            self._connection_status = "connected"
            self._qr_code = ""
            self._connected_at = datetime.now(UTC).isoformat()
            log.info("whatsapp.connected")
            await self._bus.publish(
                EventEnvelope(
                    type="gateway.whatsapp.connected",
                    source="whatsapp_gateway",
                    topic="gateway.whatsapp.connected",
                    payload={},
                )
            )

        elif etype == "reconnecting":
            self._connection_status = "reconnecting"
            log.info("whatsapp.reconnecting")

        elif etype == "disconnected":
            self._connection_status = "disconnected"
            self._running = False
            log.info("whatsapp.bridge_disconnected")
            await self._bus.publish(
                EventEnvelope(
                    type="gateway.whatsapp.disconnected",
                    source="whatsapp_gateway",
                    topic="gateway.whatsapp.disconnected",
                    payload={},
                )
            )

        elif etype == "message":
            from_number = self._normalize_number(event.get("from", ""))
            text = event.get("text", "")
            message_id = event.get("id", "") or ""
            if from_number and text:
                self._record_incoming(from_number, text)
                await self._on_incoming_message(from_number, text, message_id)

    # ── process monitor ───────────────────────────────────────────────────────

    async def _monitor_process(self) -> None:
        """Poll the bridge process and handle exit."""
        while self._running and self._process:
            await asyncio.sleep(2.0)
            if self._process.poll() is not None:
                log.info("whatsapp.bridge_exited", returncode=self._process.returncode)
                if self._running:
                    self._running = False
                    self._connection_status = "disconnected"
                    await self._bus.publish(
                        EventEnvelope(
                            type="gateway.whatsapp.disconnected",
                            source="whatsapp_gateway",
                            topic="gateway.whatsapp.disconnected",
                            payload={},
                        )
                    )
                break

    # ── stop ──────────────────────────────────────────────────────────────────

    async def stop(self) -> None:
        """Stop the WhatsApp gateway."""
        self._running = False
        if self._process:
            try:
                self._process.kill()
                await asyncio.to_thread(self._process.wait, 5.0)
            except Exception:
                pass
            self._process = None
        self._connection_status = "disconnected"
        self._connected_at = ""
        await self._bus.publish(
            EventEnvelope(
                type="gateway.whatsapp.disconnected",
                source="whatsapp_gateway",
                topic="gateway.whatsapp.disconnected",
                payload={},
            )
        )
        log.info("whatsapp.disconnected")

    # ── send ─────────────────────────────────────────────────────────────────

    async def send_message(self, to: str, text: str) -> bool:
        """Send a WhatsApp message via the bridge stdin.

        The bridge reads a JSON command ``{"type":"send","to":"...","text":"..."}``
        on stdin and delivers the message.

        Returns True on success, False if the bridge is not running or an
        error occurs.
        """
        if not self._process or self._process.poll() is not None:
            log.warning("whatsapp.send_not_running", to=to)
            return False
        try:
            payload = json.dumps({"type": "send", "to": to, "text": text})
            await asyncio.to_thread(self._write_stdin, payload)
            return True
        except Exception as exc:
            log.warning("whatsapp.send_failed", to=to, error=str(exc))
            return False

    def _write_stdin(self, line: str) -> None:
        """Write a line to the bridge stdin (blocking, run in thread)."""
        if self._process and self._process.stdin:
            self._process.stdin.write(line + "\n")
            self._process.stdin.flush()

    # ── status ────────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        # NOTE: the raw pairing QR string is a secret and is NEVER exposed here.
        # Clients get only `has_qr` (bool); the live SVG comes exclusively from
        # the dedicated /api/gateway/whatsapp/qr endpoint.
        return {
            "running": self._running,
            "connection_status": self._connection_status,
            "connected_at": self._connected_at,
            "has_qr": bool(self._qr_code),
            "recent_messages": self._recent_messages[-20:],
            "allowed_numbers": list(self._allowed_numbers) if self._allowed_numbers else None,
            "mission_count": len(self._chat_missions),
            "bridge_script": str(_BRIDGE_SCRIPT_PATH),
            "bridge_exists": _BRIDGE_SCRIPT_PATH.exists(),
        }

    # ── mission tracking ─────────────────────────────────────────────────────

    def register_mission(self, from_number: str, mission_id: str) -> None:
        """Track which phone number a mission belongs to."""
        self._chat_missions.setdefault(from_number, []).append(mission_id)
        self._mission_chats[mission_id] = from_number

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_number(raw: str) -> str:
        """Extract a bare international number from a WhatsApp JID."""
        num = (raw or "").strip()
        if "@" in num:
            num = num.split("@", 1)[0]
        return num

    def _record_incoming(self, from_number: str, text: str) -> None:
        msg = {
            "from": from_number,
            "text": text,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._recent_messages.append(msg)
        if len(self._recent_messages) > 100:
            self._recent_messages = self._recent_messages[-100:]
        log.info("whatsapp.message_received", from_number=from_number)
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(
                self._bus.publish(
                    EventEnvelope(
                        type="gateway.whatsapp.message",
                        source="whatsapp_gateway",
                        topic="gateway.whatsapp.message",
                        payload={"from": from_number, "text": text},
                    )
                )
            )
        )

    def _is_authorized(self, from_number: str) -> bool:
        if self._allowed_numbers is None:
            return True
        return from_number in self._allowed_numbers

    async def _reject_unauthorized(self, from_number: str) -> None:
        await self._bus.publish(
            EventEnvelope(
                type="audit.event",
                source="whatsapp_gateway",
                topic=Topic.AUDIT.value,
                payload={
                    "timestamp": datetime.now(UTC).isoformat(),
                    "principal": from_number,
                    "channel": CHANNEL_WHATSAPP,
                    "action": "whatsapp.access",
                    "outcome": "deny",
                    "target": "",
                    "meta": {"reason": "not_allowlisted"},
                },
            )
        )

    # ── incoming message handling (the core path) ───────────────────────────

    async def _on_incoming_message(self, from_number: str, text: str, message_id: str) -> None:
        if not self._is_authorized(from_number):
            await self._reject_unauthorized(from_number)
            return

        stripped = text.strip()
        # Command dispatch
        if stripped.startswith("/"):
            cmd, _, arg = stripped.partition(" ")
            await self._dispatch_command(from_number, cmd.lower(), arg.strip(), message_id)
            return

        # Plain text → mission prompt
        await self._submit_prompt(from_number, text, message_id)

    async def _dispatch_command(
        self, from_number: str, cmd: str, arg: str, message_id: str
    ) -> None:
        if cmd in ("/start", "/help"):
            await self.send_message(
                from_number,
                "🤖 AgenticOS — Mission Control via WhatsApp\n\n"
                "Commands:\n"
                "/mission <prompt> — Create a mission\n"
                "/status — Mission + gateway summary\n"
                "/missions — List your missions\n"
                "/result <id> — Mission detail\n"
                "/agents — List live agents\n"
                "/cancel <id> — Cancel a mission you own\n"
                "/stop <id> — Alias of /cancel\n"
                "/retry <id> — Re-run a failed mission\n\n"
                "Or just send any text — it becomes a mission prompt.",
            )
        elif cmd in ("/mission", "/prompt"):
            if not arg:
                await self.send_message(from_number, "Usage: /mission <your prompt here>")
                return
            await self._submit_prompt(from_number, arg, message_id)
        elif cmd == "/status":
            mission_ids = self._chat_missions.get(from_number, [])
            lines = [f"📋 WhatsApp gateway: {self._connection_status}"]
            if self._connected_at:
                lines.append(f"Connected: {self._connected_at}")
            if not mission_ids:
                lines.append("No missions from this number yet. Send a message to create one!")
            else:
                lines.append(f"You have {len(mission_ids)} mission(s):")
                for mid in mission_ids[-10:]:
                    m = self._remote.get_mission(mid) if self._remote else None
                    status = m.get("status", "") if m else "?"
                    title = (m.get("title", "") or "")[:40] if m else ""
                    lines.append(f"• {mid[:8]} [{status}] {title}")
            await self.send_message(from_number, "\n".join(lines))
        elif cmd == "/missions":
            if not self._remote:
                await self.send_message(from_number, "Remote prompt service is not available yet.")
                return
            missions = self._remote.list_missions()
            mine = [
                m
                for m in missions
                if self._chat_missions.get(from_number, [])
                and m["id"] in self._chat_missions[from_number]
            ]
            source = mine if mine else missions
            if not source:
                await self.send_message(
                    from_number, "No missions yet. Send a message to create one!"
                )
                return
            lines = [f"📋 {len(source)} mission(s):"]
            for m in source[:10]:
                lines.append(
                    f"• {m['id'][:8]} [{m.get('status', '')}] "
                    f"({m.get('channel', 'WEB')}) {(m.get('title', '') or '')[:40]}"
                )
            await self.send_message(from_number, "\n".join(lines))
        elif cmd == "/result":
            if not arg:
                await self.send_message(from_number, "Usage: /result <mission_id>")
                return
            m = self._remote.get_mission(arg) if self._remote else None
            if not m:
                await self.send_message(from_number, f"Mission {arg[:12]} not found.")
                return
            plan = m.get("plan") or {}
            tasks = plan.get("tasks", [])
            done = sum(1 for t in tasks if t.get("status") == "completed")
            prompt = (m.get("prompt", "") or "").strip()
            lines = [
                f"📦 Mission {m['id']}",
                f"Status: {m.get('status', '')}",
                f"Channel: {m.get('channel', 'WEB')}",
                f"Title: {(m.get('title', '') or '')[:80]}",
                f"Tasks: {done}/{len(tasks)} completed",
            ]
            if prompt:
                lines.append(f"Prompt: {prompt[:200]}")
            await self.send_message(from_number, "\n".join(lines))
        elif cmd == "/agents":
            if not self._remote:
                await self.send_message(from_number, "Remote prompt service is not available yet.")
                return
            agents = await self._remote.list_agents()
            if not agents:
                await self.send_message(from_number, "No agents registered yet.")
                return
            lines = ["🤖 Live agents:"]
            for a in agents[:20]:
                lines.append(
                    f"• {a.get('id', a.get('name', '?'))} [{a.get('status', '?')}] "
                    f"({(a.get('capabilities') or [])[:3]})"
                )
            await self.send_message(from_number, "\n".join(lines))
        elif cmd in ("/cancel", "/stop"):
            if not arg:
                await self.send_message(from_number, f"Usage: {cmd} <mission_id>")
                return
            if not self._remote:
                await self.send_message(from_number, "Remote prompt service is not available yet.")
                return
            identity = RemoteIdentity(
                channel=CHANNEL_WHATSAPP,
                external_account_id=from_number,
            )
            try:
                result = await self._remote.cancel(arg, identity)
            except Exception as exc:
                await self.send_message(
                    from_number,
                    f"⚠️ Could not cancel: {getattr(exc, 'message', exc)}",
                )
                return
            await self.send_message(
                from_number,
                f"🛑 Mission {arg[:12]} cancelled (status: {result.get('status', '')}).",
            )
        elif cmd == "/retry":
            if not arg:
                await self.send_message(from_number, "Usage: /retry <mission_id>")
                return
            original = self._remote.get_mission(arg) if self._remote else None
            if not original:
                await self.send_message(from_number, f"Mission {arg[:12]} not found.")
                return
            prompt = original.get("prompt", "") or original.get("description", "")
            if not prompt:
                await self.send_message(from_number, "Original mission has no prompt to retry.")
                return
            await self._submit_prompt(from_number, prompt, f"retry:{arg}")
        else:
            await self.send_message(
                from_number,
                f"Unknown command {cmd}. Send /help for the command list.",
            )

    async def _submit_prompt(self, from_number: str, text: str, message_id: str) -> None:
        """Route a remote prompt into the shared mission pipeline."""
        if not self._remote:
            await self.send_message(from_number, "Remote prompt service is not available yet.")
            return
        identity = RemoteIdentity(
            channel=CHANNEL_WHATSAPP,
            external_account_id=from_number,
        )
        try:
            mission = await self._remote.submit(
                prompt=text,
                identity=identity,
                message_id=message_id,
            )
        except Exception as exc:
            await self.send_message(
                from_number,
                f"⚠️ {getattr(exc, 'message', 'Mission could not be created.')}",
            )
            return
        mid = mission.get("id", "")
        self.register_mission(from_number, mid)
        title = (mission.get("title", "") or "")[:60]
        await self.send_message(
            from_number,
            f"🚀 Mission {mid[:8]} created and dispatched: {title}\n"
            f"Progress will be streamed here. Full results: Mission Control → Mission {mid}.",
        )

    # ── event callbacks (progress + results) ─────────────────────────────────

    async def _on_mission_completed(self, event: EventEnvelope) -> None:
        mission_id = event.payload.get("id", "")
        from_number = self._mission_chats.get(mission_id)
        if from_number:
            title = event.payload.get("title", "")[:60]
            await self.send_message(from_number, f"🎉 Mission {mission_id[:8]} completed: {title}")

    async def _on_mission_failed(self, event: EventEnvelope) -> None:
        mission_id = event.payload.get("id", "")
        from_number = self._mission_chats.get(mission_id)
        if from_number:
            title = event.payload.get("title", "")[:60]
            await self.send_message(from_number, f"❌ Mission {mission_id[:8]} failed: {title}")

    async def _on_progress_event(self, event: EventEnvelope) -> None:
        """Stream task-level progress to the originating number."""
        mission_id = event.payload.get("mission_id", "")
        from_number = self._mission_chats.get(mission_id)
        if not from_number:
            return
        etype = event.type
        title = (event.payload.get("title", "") or "")[:50]
        if etype == "mission.started":
            await self.send_message(
                from_number, f"🔄 Mission {mission_id[:8]} executing — progress below."
            )
        elif etype == "task.dispatched":
            agent = event.payload.get("agent", "") or ""
            await self.send_message(from_number, f"🤖 Task '{title}' → agent {agent}".strip())
        elif etype == "task.started":
            await self.send_message(from_number, f"▶️ Task '{title}' started")
        elif etype == "task.completed":
            await self.send_message(from_number, f"✅ Task '{title}' completed")
        elif etype == "task.failed":
            error = (event.payload.get("error", "") or "")[:160]
            await self.send_message(from_number, f"❌ Task '{title}' failed: {error}")

    async def _on_task_completed(self, event: EventEnvelope) -> None:
        """Backward-compatible handler (unused; kept for API stability)."""
        mission_id = event.payload.get("mission_id", "")
        from_number = self._mission_chats.get(mission_id)
        if from_number:
            title = event.payload.get("title", "")[:40]
            result = event.payload.get("result", "")[:200]
            await self.send_message(from_number, f"✅ Task: {title}\nResult: {result}")

    async def _on_task_failed(self, event: EventEnvelope) -> None:
        mission_id = event.payload.get("mission_id", "")
        from_number = self._mission_chats.get(mission_id)
        if from_number:
            title = event.payload.get("title", "")[:40]
            error = event.payload.get("error", "")[:200]
            await self.send_message(from_number, f"❌ Task: {title}\nError: {error}")


__all__ = ["WhatsAppGateway", "WhatsAppMessage"]
