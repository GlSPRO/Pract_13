import json
from urllib import error, request

from django.conf import settings


def build_start_link(token: str) -> str:
    username = settings.TELEGRAM_BOT_USERNAME.strip().lstrip("@")
    if not username:
        return ""
    return f"https://t.me/{username}?start={token}"


def send_telegram_message(chat_id: str, text: str) -> bool:
    token = settings.TELEGRAM_BOT_TOKEN.strip()
    if not token or not chat_id:
        return False
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=8) as response:
            return 200 <= response.status < 300
    except (error.URLError, TimeoutError):
        return False
