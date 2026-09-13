"""Jobicy — free public API of remote jobs, supports a geo filter."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from relocation_agent.models import Company, Job
from relocation_agent.utils import get_json, parse_datetime, strip_html


class JobicySource:
    """See https://jobicy.com/jobs-rss-feed (JSON API v2, no key required)."""

    name = "jobicy"
    URL = "https://jobicy.com/api/v2/remote-jobs"

    def __init__(self, count: int = 50, geo: str | None = None) -> None:
        self._count = count
        self._geo = geo

    def fetch(self, since: datetime, companies: Sequence[Company]) -> Iterable[Job]:  # noqa: ARG002
        """Yield jobs newer than ``since``."""
        params: dict[str, object] = {"count": self._count}
        if self._geo:
            params["geo"] = self._geo
        payload = get_json(self.URL, params=params)
        for raw in payload.get("jobs") or []:
            posted = parse_datetime(raw.get("pubDate"))
            if posted and posted < since:
                continue
            yield Job(
                title=raw.get("jobTitle", "").strip(),
                company=raw.get("companyName", "").strip(),
                url=raw.get("url", ""),
                location=raw.get("jobGeo", "") or "Anywhere",
                posted_at=posted,
                source=self.name,
                description=strip_html(raw.get("jobDescription") or raw.get("jobExcerpt")),
                remote=True,
                tags=tuple(raw.get("jobIndustry") or ()),
            )
