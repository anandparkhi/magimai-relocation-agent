"""Arbeitnow — free public API, Europe-focused, exposes a ``visa_sponsorship`` flag."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from relocation_agent.models import Company, Job
from relocation_agent.utils import get_json, get_logger, parse_datetime, strip_html

log = get_logger(__name__)


class ArbeitnowSource:
    """See https://www.arbeitnow.com/api/job-board-api (no key required)."""

    name = "arbeitnow"
    URL = "https://www.arbeitnow.com/api/job-board-api"

    def __init__(self, max_pages: int = 5, visa_only: bool = True) -> None:
        self._max_pages = max_pages
        self._visa_only = visa_only

    def fetch(self, since: datetime, companies: Sequence[Company]) -> Iterable[Job]:  # noqa: ARG002
        """Paginate newest-first and stop once a page is entirely older than ``since``."""
        for page in range(1, self._max_pages + 1):
            payload = get_json(self.URL, params={"page": page})
            rows = payload.get("data") or []
            if not rows:
                return
            oldest: datetime | None = None
            for raw in rows:
                posted = parse_datetime(raw.get("created_at"))
                if posted and (oldest is None or posted < oldest):
                    oldest = posted
                visa = bool(raw.get("visa_sponsorship"))
                if self._visa_only and not visa:
                    continue
                yield Job(
                    title=raw.get("title", "").strip(),
                    company=raw.get("company_name", "").strip(),
                    url=raw.get("url", ""),
                    location=raw.get("location", ""),
                    posted_at=posted,
                    source=self.name,
                    description=strip_html(raw.get("description")),
                    remote=bool(raw.get("remote")),
                    tags=tuple(raw.get("tags") or ()),
                    signal="Visa sponsorship (flagged by Arbeitnow)" if visa else None,
                )
            if oldest and oldest < since:
                return
