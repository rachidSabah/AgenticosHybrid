const {
  useMultiFileAuthState,
  makeWASocket,
  DisconnectReason,
  Browsers
} = require('@whiskeysockets/baileys');
const readline = require('readline');

const SESSION_PATH = process.env.WA_SESSION_PATH || 'C:\\Users\\InGodWeTrust\\.agentic_os\\whatsapp_session';
const MAX_RETRIES = 5;

let sock = null;
let retryCount = 0;

async function connect() {
  const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);

  sock = makeWASocket({
    auth: state,
    printQRInTerminal: false,
    browser: Browsers.ubuntu('Chrome'),
    // Longer keepalive to avoid premature disconnects
    keepAliveIntervalMs: 30_000,
    connectTimeoutMs: 60_000,
    retryRequestDelayMs: 2000,
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, qr, lastDisconnect } = update;

    if (qr) {
      retryCount = 0; // reset on fresh QR
      console.log(JSON.stringify({ type: 'qr', qr }));
    }

    if (connection === 'open') {
      retryCount = 0;
      console.log(JSON.stringify({ type: 'connected' }));
    }

    if (connection === 'close') {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const isLoggedOut = statusCode === DisconnectReason.loggedOut;
      const isBadSession = statusCode === DisconnectReason.badSession;

      if (isLoggedOut || isBadSession) {
        // Unrecoverable — tell Python and exit
        console.log(JSON.stringify({
          type: 'disconnected',
          reason: isLoggedOut ? 'logged_out' : 'bad_session'
        }));
        process.exit(0);
      }

      // Transient error — retry with backoff
      retryCount++;
      if (retryCount > MAX_RETRIES) {
        console.log(JSON.stringify({ type: 'disconnected', reason: 'max_retries' }));
        process.exit(1);
      }

      const delay = Math.min(1000 * Math.pow(2, retryCount - 1), 30000);
      console.log(JSON.stringify({ type: 'reconnecting', attempt: retryCount, delay_ms: delay }));

      await new Promise(r => setTimeout(r, delay));
      await connect(); // recursive reconnect
    }
  });

  sock.ev.on('messages.upsert', async (m) => {
    const msg = m.messages[0];
    if (!msg.message || msg.key.fromMe) return;
    const text =
      msg.message.conversation ||
      msg.message.extendedTextMessage?.text ||
      msg.message.imageMessage?.caption ||
      '';
    const from = msg.key.remoteJid || '';
    if (text) {
      console.log(JSON.stringify({ type: 'message', from, text }));
    }
  });
}

async function main() {
  await connect();

  // Handle send commands from Python via stdin
  const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  rl.on('line', async (line) => {
    line = line.trim();
    if (!line) return;
    try {
      const cmd = JSON.parse(line);
      if (cmd.type === 'send' && cmd.to && cmd.text && sock) {
        await sock.sendMessage(cmd.to, { text: cmd.text });
        console.log(JSON.stringify({ type: 'sent', to: cmd.to }));
      }
    } catch (err) {
      console.log(JSON.stringify({ type: 'error', message: String(err) }));
    }
  });

  // Keep alive — readline keeps loop alive but add explicit guard
  await new Promise((resolve) => rl.on('close', resolve));
}

main().catch(err => {
  process.stderr.write(String(err) + '\n');
  process.exit(1);
});