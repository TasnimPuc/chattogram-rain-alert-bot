"""Telegram Bot API: sendMessage to one or more chats (comma-separated TELEGRAM_CHAT_ID; a channel like @name works
when the bot is an admin there)."""
from __future__ import annotations

import os
import time

import requests

API = "https://api.telegram.org/bot{token}/sendMessage"


def send(text: str, token: str | None = None, chat_ids: str | None = None, post=None, tries: int = 3) -> int:
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_ids = chat_ids or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_ids:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (GitHub: Settings → Secrets → Actions).")
    post = post or requests.post
    sent = 0
    for chat in [c.strip() for c in chat_ids.split(",") if c.strip()]:
        for part in [text[i:i + 4000] for i in range(0, len(text), 4000)]:
            for i in range(tries):
                r = post(API.format(token=token), timeout=30,
                         data={"chat_id": chat, "text": part, "parse_mode": "HTML", "disable_web_page_preview": True})
                if getattr(r, "status_code", 200) == 200:
                    sent += 1
                    break
                if i == tries - 1:
                    raise RuntimeError(f"Telegram error for chat {chat}: {getattr(r, 'text', '')[:200]}")
                time.sleep(2 ** i)
    return sent
