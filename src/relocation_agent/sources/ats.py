"""Poll companies' own job boards via public ATS feeds (Greenhouse, Lever, Ashby, Teamtailor).

This is the highest-signal source: it reads directly from the employer, needs no
key, and is the only way to see *every* opening at a known sponsor.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime

import httpx

from relocation_agent.models import Company, Job
from relocation_agent.utils import get_json, get_logger, http_get, parse_datetime, strip_html

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


def _rss_field(item: ET.Element, name: str) -> str:
    """First child text whose tag (namespace stripped) equals ``name``."""
    for child in item:
        if child.tag.rsplit("}", 1)[-1] == name and child.text:
            return child.text.strip()
    return ""


def _rss(company: Company, url: str, source: str) -> Iterable[Job]:
    """Generic RSS job feed. Understands Teamtailor's extra fields when present."""
    root = ET.fromstring(http_get(url).text)
    for item in root.iter("item"):
        remote_status = _rss_field(item, "remoteStatus").lower()
        yield Job(
            title=_rss_field(item, "title"),
            company=company.name,
            url=_rss_field(item, "link"),
            location=_rss_field(item, "locations") or _rss_field(item, "location"),
            posted_at=parse_datetime(_rss_field(item, "pubDate")),
            source=source,
            description=strip_html(_rss_field(item, "description")),
            remote=remote_status in {"fully", "remote"},
            tags=tuple(filter(None, (_rss_field(item, "department"), _rss_field(item, "role")))),
        )


def _teamtailor(company: Company) -> Iterable[Job]:
    """Teamtailor career sites publish ``/jobs.rss``.

    ``ats_token`` is either the ``<slug>`` of ``<slug>.teamtailor.com`` or, for
    sites on a custom domain, the full host (``careers.example.com``).
    """
    token = company.ats_token or ""
    host = token if "." in token else f"{token}.teamtailor.com"
    return _rss(company, f"https://{host}/jobs.rss", "ats:teamtailor")


def _generic_rss(company: Company) -> Iterable[Job]:
    """Any career page that publishes an RSS feed; ``ats_token`` is the full feed URL."""
    return _rss(company, company.ats_token or "", "ats:rss")


FETCHERS: dict[str, Fetcher] = {
    "greenhouse": _greenhouse,
    "lever": _lever,
    "ashby": _ashby,
    "teamtailor": _teamtailor,
    "rss": _generic_rss,
}


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
            except (httpx.HTTPError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
                log.warning("ATS board %s/%s failed: %s", company.ats, company.ats_token, exc)
