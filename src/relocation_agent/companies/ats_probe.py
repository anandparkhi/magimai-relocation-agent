"""Guess a company's public ATS board from its name.

Cheap heuristic: try a few slug variants against each ATS board API. A 200 with
a job list is a hit. Wrong guesses cost one 404 each.
"""

from __future__ import annotations

import re

import httpx

from relocation_agent.utils import USER_AGENT, get_logger

log = get_logger(__name__)

_PROBES: dict[str, str] = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json&limit=1",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "teamtailor": "https://{slug}.teamtailor.com/jobs.rss",
}


def slug_variants(name: str) -> list[str]:
    """Candidate board slugs for ``name`` (deduplicated, most likely first)."""
    base = re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()
    words = base.split()
    candidates = ["".join(words), "-".join(words), words[0] if words else ""]
    return [c for i, c in enumerate(candidates) if c and c not in candidates[:i]]


def _looks_like_board(ats: str, resp: httpx.Response) -> bool:
    if ats == "teamtailor":
        return "<rss" in resp.text[:500]
    try:
        payload = resp.json()
    except ValueError:
        return False
    if ats == "lever":
        return isinstance(payload, list)
    return isinstance(payload, dict) and isinstance(payload.get("jobs"), list)


def probe(name: str, *, timeout: float = 10.0) -> tuple[str, str] | None:
    """Return ``(ats, token)`` if a public board is found for ``name``, else ``None``."""
    with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
        for slug in slug_variants(name):
            for ats, template in _PROBES.items():
                try:
                    resp = client.get(template.format(slug=slug))
                    if resp.status_code == 200 and _looks_like_board(ats, resp):
                        log.info("ATS probe hit: %s → %s/%s", name, ats, slug)
                        return ats, slug
                except (httpx.HTTPError, ValueError):
                    continue
    return None
