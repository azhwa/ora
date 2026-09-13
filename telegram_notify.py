import json
import logging
import os
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
        f"⏱ <b>Interval:</b> {cfg.get('min_interval_seconds', 30)} - {cfg.get('max_interval_seconds', 60)}s\n"
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
        f"⏱ <b>Running For:</b> {elapsed_str}\n"
        "<i>Still hunting for available ARM capacity...</i>"
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
        "✅ <i>Enjoy your Always Free ARM VPS!</i>"
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
