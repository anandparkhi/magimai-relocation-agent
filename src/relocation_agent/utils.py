"""Small shared helpers: HTTP with retries, time parsing, HTML stripping, logging."""

from __future__ import annotations

import html
import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

USER_AGENT = "relocation-jobs-agent/0.1 (+https://github.com/anandparkhi/magimai-relocation-agent)"
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")


def get_logger(name: str) -> logging.Logger:
    """Return a module logger configured once with a compact format."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    return logging.getLogger(name)


def utcnow() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(UTC)


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and (
        exc.response.status_code == 429 or exc.response.status_code >= 500
    )


@retry(
    retry=retry_if_exception(_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def http_get(url: str, *, params: dict[str, Any] | None = None, timeout: float = 30.0) -> httpx.Response:
    """GET with a browser-like UA and bounded retries on transient failures.

    Retries only on transport errors, 429 and 5xx. 4xx (other than 429) fail fast.

    Raises:
        httpx.HTTPStatusError: For non-2xx responses after retries are exhausted.
    """
    with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as c:
        resp = c.get(url, params=params)
        resp.raise_for_status()
        return resp


def get_json(url: str, *, params: dict[str, Any] | None = None, timeout: float = 30.0) -> Any:
    """GET and decode JSON. See :func:`http_get` for retry semantics."""
    return http_get(url, params=params, timeout=timeout).json()


def strip_html(text: str | None, limit: int | None = None) -> str:
    """Convert an HTML fragment to compact plain text.

    Args:
        text: HTML or plain text; ``None`` becomes ``""``.
        limit: Optional maximum length of the returned string.
    """
    if not text:
        return ""
    plain = html.unescape(_TAG_RE.sub(" ", text))
    plain = _WS_RE.sub(" ", plain)
    plain = re.sub(r"\n\s*\n+", "\n", plain).strip()
    return plain[:limit] if limit else plain


def parse_datetime(value: Any) -> datetime | None:
    """Parse the many timestamp shapes job APIs emit into an aware UTC datetime.

    Accepts unix seconds/milliseconds (int/float/str), ISO-8601 (with ``Z``),
    and ``YYYY-MM-DD HH:MM:SS``. Returns ``None`` when unparseable.
    """
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            number = float(value)
            if number > 1e12:  # milliseconds
                number /= 1000
            return datetime.fromtimestamp(number, tz=UTC)
        if isinstance(value, str):
            text = value.strip().replace("Z", "+00:00")
            if " " in text and "T" not in text:
                text = text.replace(" ", "T", 1)
            parsed = datetime.fromisoformat(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (ValueError, OverflowError, OSError):
        return None
    return None
