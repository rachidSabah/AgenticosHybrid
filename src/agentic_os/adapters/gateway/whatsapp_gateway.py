"""WhatsApp Gateway — submit missions and receive results via WhatsApp.

Uses @whiskeysockets/bailey (Node.js) via a subprocess bridge to connect
to WhatsApp Web. Scans a QR code for authentication, then listens for
incoming messages and creates missions.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime

from agentic_os.domain.events import EventEnvelope, Topic
from agentic_os.infrastructure.logging import get_logger
from agentic_os.ports.event_bus import EventBus

log = get_logger("gateway.whatsapp")


@dataclass
class WhatsAppMessage:
    from_number: str
    text: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# Node.js bridge script for Bailey WhatsApp connection
_BRIDGE_SCRIPT = """
const bailey = require('@whiskeysockets/bailey');
const readline = require('readline');

const SESSION_PATH = process.env.WA_SESSION_PATH || '/tmp/whatsapp_session';

async function main() {
    const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);
    const sock = makeWASocket({ auth: state, printQRInTerminal: false });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', (update) => {
        const { connection, qr, lastDisconnect } = update;
        if (qr) {
            console.log(JSON.stringify({ type: 'qr', qr }));
        }
        if (connection === 'open') {
            console.log(JSON.stringify({ type: 'connected' }));
        }
        if (connection === 'close') {
            const code = lastDisconnect?.error?.output?.statusCode || 0;
            if (code !== DisconnectReason.loggedOut) {
                console.log(JSON.stringify({ type: 'reconnecting' }));
                main();
            } else {
                console.log(JSON.stringify({ type: 'disconnected' }));
                process.exit(0);
            }
        }
    });

    sock.ev.on('messages.upsert', async (m) => {
        const msg = m.messages[0];
        if (!msg.message || msg.key.fromMe) return;
        const text = msg.message.conversation || msg.message.extendedTextMessage?.text || '';
        const from = msg.key.remoteJid || '';
        if (text) {
            console.log(JSON.stringify({ type: 'message', from, text }));
        }
    });

    // Read commands from stdin (for sending messages)
    const rl = readline.createInterface({ input: process.stdin });
    rl.on('line', async (line) => {
        try {
            const cmd = JSON.parse(line);
            if (cmd.type === 'send' && cmd.to && cmd.text) {
                await sock.sendMessage(cmd.to, { text: cmd.text });
                console.log(JSON.stringify({ type: 'sent', to: cmd.to }));
            }
        } catch (e) {}
    });
}

main().catch(err => console.error(err));
"""


class WhatsAppGateway:
    """WhatsApp gateway using Bailey via Node.js subprocess.

    The Node.js bridge connects to WhatsApp Web and communicates via
    stdin/stdout JSON messages.
    """

    def __init__(
        self,
        bus: EventBus,
        session_path: str = "",
    ) -> None:
        self._bus = bus
        self._session_path = session_path or os.path.expanduser("~/.agentic_os/whatsapp_session")
        self._process: asyncio.subprocess.Process | None = None
        self._running = False
        self._qr_code: str = ""
        self._connection_status: str = "disconnected"
        self._recent_messages: list[dict] = []
        self._chat_missions: dict[str, list[str]] = {}
        self._mission_chats: dict[str, str] = {}

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def qr_code(self) -> str:
        return self._qr_code

    @property
    def connection_status(self) -> str:
        return self._connection_status

    async def start(self) -> None:
        """Start the WhatsApp gateway."""
        os.makedirs(self._session_path, exist_ok=True)

        # Write the bridge script
        bridge_path = os.path.join(tempfile.gettempdir(), "wa_bridge.js")
        with open(bridge_path, "w") as f:
            f.write(_BRIDGE_SCRIPT)

        env = {**os.environ, "WA_SESSION_PATH": self._session_path}
        try:
            self._process = await asyncio.create_subprocess_exec(
                "node",
                bridge_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError:
            log.error("whatsapp.node_not_found", message="Node.js is required for WhatsApp gateway")
            return
        except Exception as exc:
            log.error("whatsapp.start_failed", error=str(exc))
            return

        self._running = True
        self._connection_status = "connecting"

        # Read stdout for events
        asyncio.create_task(self._read_stdout())
        # Read stderr for errors
        asyncio.create_task(self._read_stderr())

        # Subscribe to mission/task events
        await self._bus.subscribe(Topic.MISSION_COMPLETED.value, self._on_mission_completed)
        await self._bus.subscribe(Topic.MISSION_FAILED.value, self._on_mission_failed)
        await self._bus.subscribe("task.completed", self._on_task_completed)
        await self._bus.subscribe("task.failed", self._on_task_failed)

        log.info("whatsapp.gateway_started")

    async def stop(self) -> None:
        """Stop the WhatsApp gateway."""
        if self._process:
            self._process.kill()
            await self._process.wait()
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
        log.info("whatsapp.disconnected")

    async def _read_stdout(self) -> None:
        """Read JSON events from the Node.js bridge stdout."""
        if not self._process or not self._process.stdout:
            return
        while self._running and self._process:
            try:
                line = await self._process.stdout.readline()
                if not line:
                    break
                data = json.loads(line.decode("utf-8", errors="replace").strip())
                await self._handle_bridge_event(data)
            except json.JSONDecodeError:
                continue
            except Exception:
                break

    async def _read_stderr(self) -> None:
        """Log stderr from the bridge."""
        if not self._process or not self._process.stderr:
            return
        while self._running and self._process:
            try:
                line = await self._process.stderr.readline()
                if not line:
                    break
                log.debug(
                    "whatsapp.bridge_stderr", line=line.decode("utf-8", errors="replace").strip()
                )
            except Exception:
                break

    async def _handle_bridge_event(self, data: dict) -> None:
        """Handle events from the Node.js bridge."""
        event_type = data.get("type", "")

        if event_type == "qr":
            self._qr_code = data.get("qr", "")
            self._connection_status = "scanning"
            await self._bus.publish(
                EventEnvelope(
                    type="gateway.whatsapp.qr",
                    source="whatsapp_gateway",
                    topic="gateway.whatsapp.qr",
                    payload={"qr": self._qr_code},
                )
            )
            log.info("whatsapp.qr_generated")

        elif event_type == "connected":
            self._connection_status = "connected"
            self._qr_code = ""
            await self._bus.publish(
                EventEnvelope(
                    type="gateway.whatsapp.connected",
                    source="whatsapp_gateway",
                    topic="gateway.whatsapp.connected",
                    payload={},
                )
            )
            log.info("whatsapp.connected")

        elif event_type == "disconnected":
            self._connection_status = "disconnected"
            await self._bus.publish(
                EventEnvelope(
                    type="gateway.whatsapp.disconnected",
                    source="whatsapp_gateway",
                    topic="gateway.whatsapp.disconnected",
                    payload={},
                )
            )
            log.warning("whatsapp.disconnected")

        elif event_type == "message":
            from_number = data.get("from", "")
            text = data.get("text", "")
            self._recent_messages.append(
                {
                    "from": from_number,
                    "text": text,
                    "direction": "incoming",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            await self._bus.publish(
                EventEnvelope(
                    type="gateway.whatsapp.message_received",
                    source="whatsapp_gateway",
                    topic="gateway.whatsapp.message_received",
                    payload={"from": from_number, "text": text},
                )
            )
            log.info("whatsapp.message_received", sender=from_number, text=text[:50])

        elif event_type == "sent":
            await self._bus.publish(
                EventEnvelope(
                    type="gateway.whatsapp.message_sent",
                    source="whatsapp_gateway",
                    topic="gateway.whatsapp.message_sent",
                    payload={"to": data.get("to", "")},
                )
            )

    async def send_message(self, to: str, text: str) -> bool:
        """Send a WhatsApp message via the bridge."""
        if not self._process or not self._process.stdin:
            return False
        try:
            cmd = json.dumps({"type": "send", "to": to, "text": text}) + "\n"
            self._process.stdin.write(cmd.encode())
            await self._process.stdin.drain()
            self._recent_messages.append(
                {
                    "to": to,
                    "text": text,
                    "direction": "outgoing",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            log.info("whatsapp.message_sent", to=to, text=text[:50])
            return True
        except Exception as exc:
            log.error("whatsapp.send_failed", error=str(exc))
            return False

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "connection_status": self._connection_status,
            "qr_code": self._qr_code,
            "has_qr": bool(self._qr_code),
            "recent_messages": self._recent_messages[-20:],
        }

    def register_mission(self, from_number: str, mission_id: str) -> None:
        """Track which phone number a mission belongs to."""
        self._chat_missions.setdefault(from_number, []).append(mission_id)
        self._mission_chats[mission_id] = from_number

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
