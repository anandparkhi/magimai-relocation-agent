"""Remotive — free public API of remote jobs with a required-location field."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from relocation_agent.models import Company, Job
from relocation_agent.utils import get_json, parse_datetime, strip_html


class RemotiveSource:
    """See https://remotive.com/api/remote-jobs (no key required)."""

    name = "remotive"
    URL = "https://remotive.com/api/remote-jobs"

    def __init__(self, limit: int | None = None) -> None:
        self._limit = limit

    def fetch(self, since: datetime, companies: Sequence[Company]) -> Iterable[Job]:  # noqa: ARG002
        """Yield all jobs newer than ``since`` (API returns a single list, newest first)."""
        params = {"limit": self._limit} if self._limit else None
        payload = get_json(self.URL, params=params)
        for raw in payload.get("jobs") or []:
            posted = parse_datetime(raw.get("publication_date"))
            if posted and posted < since:
                break
            yield Job(
                title=raw.get("title", "").strip(),
                company=raw.get("company_name", "").strip(),
                url=raw.get("url", ""),
                location=raw.get("candidate_required_location", "") or "Worldwide",
                posted_at=posted,
                source=self.name,
                description=strip_html(raw.get("description")),
                remote=True,
                tags=tuple(raw.get("tags") or ()),
            )
