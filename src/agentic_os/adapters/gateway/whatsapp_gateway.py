"""WhatsApp Gateway — submit missions and receive results via WhatsApp.

Uses @whiskeysockets/baileys (Node.js) via a standalone bridge script at
E:/Agenticos/wa_bridge.js to connect to WhatsApp Web.  Scans a QR code for
authentication, then listens for incoming messages and creates missions.

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

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("gateway.whatsapp")

# ── constants ────────────────────────────────────────────────────────────────

# Absolute path to the pre-written bridge script — never computed at runtime.
# This avoids the cwd / __file__ resolution issue inside ``uv run``.
_PROJECT_ROOT = Path("E:/Agenticos")
_BRIDGE_SCRIPT_PATH = _PROJECT_ROOT / "wa_bridge.js"


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
    ) -> None:
        self._bus = bus
        self._session_path = session_path or os.path.expanduser("~/.agentic_os/whatsapp_session")
        self._process: subprocess.Popen | None = None
        self._running = False
        self._qr_code: str = ""
        self._connection_status: str = "disconnected"
        self._recent_messages: list[dict] = []
        self._chat_missions: dict[str, list[str]] = {}
        self._mission_chats: dict[str, str] = {}
        self._reader_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

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

        # Subscribe to mission/task completion events so we can reply via WA
        await self._bus.subscribe(Topic.MISSION_COMPLETED.value, self._on_mission_completed)
        await self._bus.subscribe(Topic.MISSION_FAILED.value, self._on_mission_failed)
        await self._bus.subscribe("task.completed", self._on_task_completed)
        await self._bus.subscribe("task.failed", self._on_task_failed)

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
            await self._bus.publish(
                EventEnvelope(
                    type="gateway.whatsapp.qr",
                    source="whatsapp_gateway",
                    topic="gateway.whatsapp.qr",
                    payload={"qr": self._qr_code},
                )
            )

        elif etype == "connected":
            self._connection_status = "connected"
            self._qr_code = ""
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
            from_number = event.get("from", "")
            text = event.get("text", "")
            if from_number and text:
                msg = {
                    "from": from_number,
                    "text": text,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                self._recent_messages.append(msg)
                # Keep only last 100 messages in memory
                if len(self._recent_messages) > 100:
                    self._recent_messages = self._recent_messages[-100:]
                log.info("whatsapp.message_received", from_number=from_number)
                await self._bus.publish(
                    EventEnvelope(
                        type="gateway.whatsapp.message",
                        source="whatsapp_gateway",
                        topic="gateway.whatsapp.message",
                        payload={"from": from_number, "text": text},
                    )
                )

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
        return {
            "running": self._running,
            "connection_status": self._connection_status,
            "qr_code": self._qr_code,
            "has_qr": bool(self._qr_code),
            "recent_messages": self._recent_messages[-20:],
            "bridge_script": str(_BRIDGE_SCRIPT_PATH),
            "bridge_exists": _BRIDGE_SCRIPT_PATH.exists(),
        }

    # ── mission tracking ─────────────────────────────────────────────────────

    def register_mission(self, from_number: str, mission_id: str) -> None:
        """Track which phone number a mission belongs to."""
        self._chat_missions.setdefault(from_number, []).append(mission_id)
        self._mission_chats[mission_id] = from_number

    # ── event callbacks ──────────────────────────────────────────────────────

    async def _on_mission_completed(self, event: EventEnvelope) -> None:
        mission_id = event.payload.get("id", "")
        from_number = self._mission_chats.get(mission_id)
        if from_number:
            title = event.payload.get("title", "")[:60]
            await self.send_message(from_number, f"🎉 Mission completed: {title}")

    async def _on_mission_failed(self, event: EventEnvelope) -> None:
        mission_id = event.payload.get("id", "")
        from_number = self._mission_chats.get(mission_id)
        if from_number:
            title = event.payload.get("title", "")[:60]
            await self.send_message(from_number, f"❌ Mission failed: {title}")

    async def _on_task_completed(self, event: EventEnvelope) -> None:
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
