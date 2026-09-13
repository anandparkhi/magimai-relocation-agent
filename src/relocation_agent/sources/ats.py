"""Poll companies' own job boards via public ATS JSON APIs (Greenhouse, Lever, Ashby).

This is the highest-signal source: it reads directly from the employer, needs no
key, and is the only way to see *every* opening at a known sponsor.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime

import httpx

from relocation_agent.models import Company, Job
from relocation_agent.utils import get_json, get_logger, parse_datetime, strip_html

log = get_logger(__name__)

Fetcher = Callable[[Company], Iterable[Job]]


def _greenhouse(company: Company) -> Iterable[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{company.ats_token}/jobs"
    payload = get_json(url, params={"content": "true"})
    for raw in payload.get("jobs") or []:
        location = (raw.get("location") or {}).get("name", "")
        yield Job(
            title=raw.get("title", "").strip(),
            company=company.name,
            url=raw.get("absolute_url", ""),
            location=location,
            posted_at=parse_datetime(raw.get("first_published") or raw.get("updated_at")),
            source="ats:greenhouse",
            description=strip_html(raw.get("content")),
            remote="remote" in location.lower(),
        )


def _lever(company: Company) -> Iterable[Job]:
    url = f"https://api.lever.co/v0/postings/{company.ats_token}"
    for raw in get_json(url, params={"mode": "json"}) or []:
        categories = raw.get("categories") or {}
        yield Job(
            title=raw.get("text", "").strip(),
            company=company.name,
            url=raw.get("hostedUrl", ""),
            location=categories.get("location", "") or categories.get("allLocations", [""])[0],
            posted_at=parse_datetime(raw.get("createdAt")),
            source="ats:lever",
            description=strip_html(raw.get("descriptionPlain") or raw.get("description")),
            remote=(raw.get("workplaceType") or "").lower() == "remote",
            tags=tuple(filter(None, (categories.get("team"), categories.get("commitment")))),
        )


def _ashby(company: Company) -> Iterable[Job]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company.ats_token}"
    payload = get_json(url, params={"includeCompensation": "false"})
    for raw in payload.get("jobs") or []:
        yield Job(
            title=raw.get("title", "").strip(),
            company=company.name,
            url=raw.get("jobUrl", ""),
            location=raw.get("location", ""),
            posted_at=parse_datetime(raw.get("publishedAt")),
            source="ats:ashby",
            description=strip_html(raw.get("descriptionPlain") or raw.get("descriptionHtml")),
            remote=bool(raw.get("isRemote")),
            tags=tuple(filter(None, (raw.get("department"), raw.get("team")))),
        )


FETCHERS: dict[str, Fetcher] = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby}


class ATSSource:
    """Iterates every company with an ``ats``/``ats_token`` and pulls its board.

    A failing board (404 for a wrong token, timeout, schema change) is logged
    and skipped so a single company never breaks the run.
    """

    name = "ats"

    def fetch(self, since: datetime, companies: Sequence[Company]) -> Iterable[Job]:
        """Yield board postings newer than ``since`` across all ATS-enabled companies."""
        for company in companies:
            fetcher = FETCHERS.get(company.ats or "")
            if not fetcher or not company.ats_token:
                continue
            try:
                for job in fetcher(company):
                    if job.posted_at is None or job.posted_at >= since:
                        yield job
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                log.warning("ATS board %s/%s failed: %s", company.ats, company.ats_token, exc)
