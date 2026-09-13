"""Telegram channel/group publisher — free, no link surcharge."""

from __future__ import annotations

import httpx

from relocation_agent.publisher.base import PublishError


class TelegramPublisher:
    """Posts via the Bot API ``sendMessage`` endpoint."""

    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id

    def publish(self, text: str, *, url: str | None = None) -> str:
        """Send the message, appending the job URL (Telegram links are free)."""
        body = f"{text}\n{url}" if url and url not in text else text
        try:
            resp = httpx.post(
                self._url,
                json={"chat_id": self._chat_id, "text": body, "disable_web_page_preview": False},
                timeout=20,
            )
            resp.raise_for_status()
            payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PublishError(f"Telegram send failed: {exc}") from exc
        if not payload.get("ok"):
            raise PublishError(f"Telegram error: {payload.get('description')}")
        return str(payload["result"]["message_id"])
