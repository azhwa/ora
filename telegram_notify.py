import datetime
import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
import uuid
from typing import Optional

logger = logging.getLogger("telegram_notify")


def send_telegram_message(
    bot_token: Optional[str],
    chat_id: Optional[str],
    text: str,
    parse_mode: str = "HTML"
) -> bool:
    """Sends a message via Telegram Bot API using only Python standard library."""
    if not bot_token or not chat_id:
        logger.debug("Telegram credentials not configured; skipping notification.")
        return False

    url = f"https://api.telegram.org/bot{bot_token.strip()}/sendMessage"
    payload = {
        "chat_id": str(chat_id).strip(),
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
            return bool(result.get("ok"))
    except Exception as e:
        logger.warning(f"Failed to send Telegram notification: {e}")
        return False


def build_multipart_body(fields: dict, files: dict, boundary: str) -> bytes:
    """Builds multipart/form-data payload without third-party dependencies."""
    buffer = bytearray()
    for name, value in fields.items():
        buffer.extend(f"--{boundary}\r\n".encode("utf-8"))
        buffer.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        buffer.extend(str(value).encode("utf-8"))
        buffer.extend(b"\r\n")

    for name, (filename, content) in files.items():
        buffer.extend(f"--{boundary}\r\n".encode("utf-8"))
        buffer.extend(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8"))
        buffer.extend(b"Content-Type: application/octet-stream\r\n\r\n")
        buffer.extend(content)
        buffer.extend(b"\r\n")

    buffer.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return bytes(buffer)


def send_telegram_document(
    bot_token: Optional[str],
    chat_id: Optional[str],
    file_path: str,
    caption: str = "",
) -> bool:
    """Sends a document/file to Telegram using multipart/form-data (zero dependencies)."""
    if not bot_token or not chat_id:
        return False

    resolved_path = os.path.expanduser(file_path)
    if not os.path.isfile(resolved_path):
        logger.warning(f"File not found for Telegram document upload: {resolved_path}")
        return False

    url = f"https://api.telegram.org/bot{bot_token.strip()}/sendDocument"
    boundary = f"----TelegramUploadBoundary{uuid.uuid4().hex}"
    filename = os.path.basename(resolved_path)

    try:
        with open(resolved_path, "rb") as f:
            file_bytes = f.read()

        fields = {"chat_id": str(chat_id).strip()}
        if caption:
            fields["caption"] = caption
            fields["parse_mode"] = "HTML"

        files = {"document": (filename, file_bytes)}
        body = build_multipart_body(fields, files, boundary)

        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            return bool(result.get("ok"))
    except Exception as e:
        logger.warning(f"Failed to upload document to Telegram: {e}")
        return False


def notify_startup(bot_token: str, chat_id: str, cfg: dict) -> bool:
    msg = (
        "🚀 <b>Oracle ARM Hunter Started!</b>\n\n"
        f"📍 <b>Region:</b> <code>{cfg.get('region')}</code>\n"
        f"💻 <b>Shape:</b> <code>{cfg.get('shape', 'VM.Standard.A1.Flex')}</code>\n"
        f"⚡ <b>Specs:</b> {cfg.get('ocpus', 1)} OCPU / {cfg.get('memory_in_gbs', 4)} GB RAM\n"
        f"💿 <b>OS:</b> {cfg.get('operating_system', 'Canonical Ubuntu')} {cfg.get('os_version', '24.04')}\n"
        f"⏱ <b>Interval:</b> {cfg.get('min_interval_seconds', 30)} - {cfg.get('max_interval_seconds', 60)}s\n\n"
        "🎮 <b>Kontrol Bot via Chat:</b>\n"
        "📊 <code>/status</code> - Cek status terkini\n"
        "⏸️ <code>/stop</code> - Jeda pemburuan sementara\n"
        "▶️ <code>/start</code> - Lanjutkan pemburuan\n"
        "🛑 <code>/exit</code> - Matikan bot di PM2\n\n"
        "🎯 <i>Monitoring capacity in the background...</i>"
    )
    return send_telegram_message(bot_token, chat_id, msg)


def notify_heartbeat(
    bot_token: str,
    chat_id: str,
    attempts: int,
    capacity_hits: int,
    current_ad: str,
    elapsed_str: str
) -> bool:
    msg = (
        "⏳ <b>Oracle Hunter Heartbeat</b>\n\n"
        f"🔄 <b>Total Attempts:</b> {attempts}\n"
        f"🚫 <b>Capacity Hits:</b> {capacity_hits}\n"
        f"📍 <b>Last AD:</b> <code>{current_ad}</code>\n"
        f"⏱ <b>Running For:</b> {elapsed_str}\n\n"
        "💡 <i>Ketik /status untuk detail lengkap, atau /stop untuk menjeda.</i>"
    )
    return send_telegram_message(bot_token, chat_id, msg)


def notify_success(
    bot_token: str,
    chat_id: str,
    instance_id: str,
    public_ip: Optional[str],
    shape: str,
    ocpus: int,
    memory_gb: int,
    ssh_user: str = "ubuntu",
    ssh_key_path: str = "~/.ssh/id_rsa",
    local_pc_key_name: str = "oraclehost_id_rsa"
) -> bool:
    ip_display = public_ip or "Pending / No Public IP"

    # Command using the local private key from the bot host
    bot_host_cmd = f"ssh -i {ssh_key_path} {ssh_user}@{public_ip}" if public_ip else "N/A"
    # Command using the user's laptop key
    laptop_cmd = f"ssh -i ~/.ssh/{local_pc_key_name} {ssh_user}@{public_ip}" if public_ip else "N/A"

    msg = (
        "🎉 <b>SUCCESS! Oracle ARM Instance Created!</b> 🎉\n\n"
        f"🌐 <b>Public IP:</b> <code>{ip_display}</code>\n"
        f"⚡ <b>Specs:</b> {ocpus} OCPU / {memory_gb} GB RAM ({shape})\n"
        f"🆔 <b>Instance OCID:</b>\n<code>{instance_id}</code>\n\n"
        "🔑 <b>Login via SSH (User: <code>ubuntu</code>):</b>\n\n"
        f"💻 <b>From your Laptop/PC:</b>\n"
        f"<code>{laptop_cmd}</code>\n\n"
        f"🖥 <b>From the Hunter VPS:</b>\n"
        f"<code>{bot_host_cmd}</code>\n\n"
        "📎 <i>Private key file is being attached below for mobile/backup access.</i>\n"
        "✅ <i>Bot has automatically stopped in PM2. Enjoy your Always Free ARM VPS!</i>"
    )
    send_telegram_message(bot_token, chat_id, msg)

    # Attach private key document directly to Telegram chat
    resolved_priv = os.path.expanduser(ssh_key_path)
    if os.path.isfile(resolved_priv):
        send_telegram_document(
            bot_token,
            chat_id,
            resolved_priv,
            caption=(
                f"🔑 <b>Private Key for {public_ip or 'New Instance'}</b>\n"
                f"Username: <code>{ssh_user}</code>\n"
                f"Set permission: <code>chmod 600 {os.path.basename(resolved_priv)}</code>"
            ),
        )
    return True


def notify_abort(bot_token: str, chat_id: str, reason: str) -> bool:
    msg = (
        "🛑 <b>Oracle ARM Hunter Stopped (Fatal Error)</b>\n\n"
        f"<b>Reason:</b>\n<code>{reason}</code>\n\n"
        "⚠️ <i>Please check your Oracle Cloud account limits or configuration.</i>"
    )
    return send_telegram_message(bot_token, chat_id, msg)


class TelegramBotListener(threading.Thread):
    """
    Background listener for incoming Telegram commands.
    Allows controlling hunter (start/stop/status/exit) directly from Telegram chat.
    """

    def __init__(self, bot_token: Optional[str], authorized_chat_id: Optional[str], state: dict, cfg: dict):
        super().__init__(daemon=True, name="TelegramListener")
        self.bot_token = bot_token.strip() if bot_token else ""
        self.authorized_chat_id = str(authorized_chat_id).strip() if authorized_chat_id else ""
        self.state = state
        self.cfg = cfg
        self.last_update_id = 0
        self.running = True

    def flush_old_updates(self):
        """Discards messages sent before listener started so they aren't re-executed."""
        if not self.bot_token:
            return
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates?offset=-1"
            req = urllib.request.Request(url, headers={"User-Agent": "OracleHunterBot/1.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                res = json.loads(response.read().decode("utf-8"))
                if res.get("ok") and res.get("result"):
                    self.last_update_id = res["result"][-1]["update_id"] + 1
        except Exception:
            pass

    def run(self):
        if not self.bot_token or not self.authorized_chat_id:
            logger.info("Telegram command listener disabled (token or chat_id missing).")
            return

        self.flush_old_updates()
        logger.info("📱 Telegram command listener started (Accepting /status, /stop, /start, /exit)...")

        while self.running:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates?offset={self.last_update_id}&timeout=10"
                req = urllib.request.Request(url, headers={"User-Agent": "OracleHunterBot/1.0"})
                with urllib.request.urlopen(req, timeout=15) as response:
                    res = json.loads(response.read().decode("utf-8"))
                    if not res.get("ok"):
                        time.sleep(2)
                        continue

                    for update in res.get("result", []):
                        self.last_update_id = update["update_id"] + 1
                        msg = update.get("message", {})
                        from_user = msg.get("from", {})
                        chat = msg.get("chat", {})
                        from_id = str(from_user.get("id") or chat.get("id") or "")
                        text = msg.get("text", "").strip()

                        # Security check: Only process messages from authorized user
                        if from_id != self.authorized_chat_id:
                            continue

                        self.handle_command(text)
            except Exception:
                time.sleep(3)

    def handle_command(self, text: str):
        cmd = text.split()[0].lower() if text else ""
        if "@" in cmd:
            cmd = cmd.split("@")[0]

        if cmd in ["/status", "/cek", "status", "cek"]:
            status_text = "⏸️ <b>DIJEDA (PAUSED)</b>" if self.state.get("paused") else "🟢 <b>AKTIF BERBURU (HUNTING)</b>"
            start_t = self.state.get("start_time", datetime.datetime.utcnow())
            elapsed = datetime.datetime.utcnow() - start_t
            elapsed_str = str(datetime.timedelta(seconds=int(elapsed.total_seconds())))

            msg = (
                "📊 <b>Status Oracle ARM Hunter</b>\n\n"
                f"⚡ <b>Kondisi:</b> {status_text}\n"
                f"🔄 <b>Total Percobaan:</b> {self.state.get('attempts', 0)}\n"
                f"🚫 <b>Kapasitas Penuh (429):</b> {self.state.get('capacity_hits', 0)}\n"
                f"📍 <b>AD Terakhir:</b> <code>{self.state.get('current_ad', 'N/A')}</code>\n"
                f"⏱ <b>Aktif Selama:</b> {elapsed_str}\n"
                f"💻 <b>Target:</b> {self.cfg.get('ocpus', 1)} OCPU / {self.cfg.get('memory_in_gbs', 4)} GB RAM\n\n"
                "<i>Perintah Cepat:</i>\n"
                "▶️ /start - Lanjutkan berburu\n"
                "⏸️ /stop - Jeda sementara\n"
                "📊 /status - Cek status terkini\n"
                "🛑 /exit - Matikan proses di PM2"
            )
            send_telegram_message(self.bot_token, self.authorized_chat_id, msg)

        elif cmd in ["/stop", "/pause", "stop", "pause"]:
            if self.state.get("paused"):
                send_telegram_message(
                    self.bot_token,
                    self.authorized_chat_id,
                    "⚠️ <b>Bot sudah dalam keadaan dijeda (Paused).</b>\n\nKetik /start untuk melanjutkan."
                )
            else:
                self.state["paused"] = True
                msg = (
                    "⏸️ <b>Pemburuan Dijeda!</b>\n\n"
                    "Bot sementara berhenti mengirim permintaan ke Oracle Cloud.\n"
                    "Ketik /start kapan saja untuk melanjutkan berburu."
                )
                send_telegram_message(self.bot_token, self.authorized_chat_id, msg)
                logger.info("⏸️ Hunter paused via Telegram command.")

        elif cmd in ["/start", "/resume", "start", "resume"]:
            if not self.state.get("paused"):
                send_telegram_message(
                    self.bot_token,
                    self.authorized_chat_id,
                    "🟢 <b>Bot sudah aktif berburu!</b>\n\nKetik /status untuk melihat progres."
                )
            else:
                self.state["paused"] = False
                msg = (
                    "▶️ <b>Pemburuan Dilanjutkan!</b>\n\n"
                    "Bot mulai mencari kapasitas ARM kembali di Oracle Cloud... 🏹"
                )
                send_telegram_message(self.bot_token, self.authorized_chat_id, msg)
                logger.info("▶️ Hunter resumed via Telegram command.")

        elif cmd in ["/exit", "/kill", "/shutdown"]:
            send_telegram_message(
                self.bot_token,
                self.authorized_chat_id,
                "🛑 <b>Oracle Hunter Dimatikan di PM2!</b>\n\nProses di VPS telah dihentikan. Untuk menyalakan kembali, login ke VPS dan ketik:\n<code>pm2 restart oracle-hunter</code>"
            )
            logger.info("🛑 Hunter shutting down via Telegram command.")
            self.running = False
            os.system("pm2 stop oracle-hunter 2>/dev/null || true")
            os._exit(0)

        elif cmd in ["/help", "help", "/menu", "menu"]:
            msg = (
                "🤖 <b>Menu Perintah Oracle Hunter:</b>\n\n"
                "📊 /status - Cek status pencarian saat ini\n"
                "⏸️ /stop - Jeda pemburuan sementara\n"
                "▶️ /start - Lanjutkan pemburuan\n"
                "🛑 /exit - Hentikan bot secara permanen di PM2"
            )
            send_telegram_message(self.bot_token, self.authorized_chat_id, msg)

