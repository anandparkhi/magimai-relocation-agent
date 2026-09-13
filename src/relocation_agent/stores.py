"""JSON-file state: seen jobs, the publish queue and the company list.

Files are small, human-readable and committed back to the repository by the
workflows, which gives free persistence plus a full audit trail in git history.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from relocation_agent.models import Company, Job
from relocation_agent.utils import utcnow


class JsonStore:
    """Base class: atomic load/save of a JSON document."""

    default: dict[str, Any] = {}

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return json.loads(json.dumps(self.default))
        with self.path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def save(self) -> None:
        """Write atomically (temp file + rename) so CI never commits a torn file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, ensure_ascii=False, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, self.path)


class SeenStore(JsonStore):
    """Every job id we have evaluated, with the outcome, for de-duplication."""

    default = {"jobs": {}}

    def has(self, job_id: str) -> bool:
        """Whether the job was already evaluated."""
        return job_id in self.data["jobs"]

    def add(self, job: Job, *, accepted: bool, now: datetime | None = None) -> None:
        """Record an evaluation outcome."""
        self.data["jobs"][job.id] = {
            "company": job.company,
            "regions": list(job.regions),
            "accepted": accepted,
            "seen_at": (now or utcnow()).isoformat(),
        }

    def prune(self, keep_days: int = 45) -> int:
        """Drop entries older than ``keep_days``; returns how many were removed."""
        cutoff = utcnow() - timedelta(days=keep_days)
        before = len(self.data["jobs"])
        self.data["jobs"] = {
            k: v for k, v in self.data["jobs"].items() if datetime.fromisoformat(v["seen_at"]) >= cutoff
        }
        return before - len(self.data["jobs"])

    def accepted_companies(self, window_days: int) -> dict[str, set[str]]:
        """Company name → union of regions for accepted jobs within the window."""
        cutoff = utcnow() - timedelta(days=window_days)
        out: dict[str, set[str]] = {}
        for entry in self.data["jobs"].values():
            if not entry.get("accepted") or datetime.fromisoformat(entry["seen_at"]) < cutoff:
                continue
            out.setdefault(entry["company"], set()).update(entry.get("regions", []))
        return out


class QueueStore(JsonStore):
    """FIFO of accepted jobs awaiting publication plus rate-limit bookkeeping."""

    default = {"items": [], "posted": {}, "last_posted_at": None, "history": []}

    def __len__(self) -> int:
        """Number of queued items."""
        return len(self.data["items"])

    def enqueue(self, jobs: Iterable[Job]) -> int:
        """Append jobs not already queued or published; returns count added."""
        known = {item["id"] for item in self.data["items"]} | {item["id"] for item in self.data["history"]}
        added = 0
        for job in jobs:
            if job.id in known:
                continue
            self.data["items"].append(job.to_dict())
            known.add(job.id)
            added += 1
        return added

    def posted_today(self, now: datetime) -> int:
        """Posts already made on ``now``'s UTC date."""
        return int(self.data["posted"].get(now.date().isoformat(), 0))

    def can_post(self, now: datetime, *, daily_cap: int, min_gap_minutes: int) -> bool:
        """Whether the daily cap and minimum spacing both allow a post right now."""
        if self.posted_today(now) >= daily_cap:
            return False
        last = self.data.get("last_posted_at")
        return not (last and now - datetime.fromisoformat(last) < timedelta(minutes=min_gap_minutes))

    def peek(self) -> Job | None:
        """Next job to publish without removing it."""
        return Job.from_dict(self.data["items"][0]) if self.data["items"] else None

    def mark_published(self, job: Job, *, now: datetime, receipts: dict[str, str]) -> None:
        """Move ``job`` from the queue to history and update rate counters."""
        self.data["items"] = [i for i in self.data["items"] if i["id"] != job.id]
        day = now.date().isoformat()
        self.data["posted"][day] = self.posted_today(now) + 1
        self.data["last_posted_at"] = now.isoformat()
        entry = job.to_dict() | {"published_at": now.isoformat(), "receipts": receipts}
        self.data["history"].insert(0, entry)
        self.data["history"] = self.data["history"][:500]
        self.data["posted"] = {
            d: n
            for d, n in self.data["posted"].items()
            if datetime.fromisoformat(d).date() >= (now - timedelta(days=14)).date()
        }

    def drop(self, job: Job) -> None:
        """Remove a job that can no longer be published (e.g. expired)."""
        self.data["items"] = [i for i in self.data["items"] if i["id"] != job.id]

    def expire(self, max_age_hours: int) -> int:
        """Drop queued items older than ``max_age_hours`` (stale news is spam)."""
        cutoff = utcnow() - timedelta(hours=max_age_hours)
        before = len(self)
        self.data["items"] = [
            i
            for i in self.data["items"]
            if not i.get("posted_at") or datetime.fromisoformat(i["posted_at"]) >= cutoff
        ]
        return before - len(self)

    def recent_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Most recently published entries, newest first."""
        return list(self.data["history"][:limit])


class CompanyStore(JsonStore):
    """The current company list, keyed by normalised name."""

    default = {"companies": [], "refreshed_at": None}

    def all(self) -> list[Company]:
        """All companies as models."""
        return [Company.from_dict(c) for c in self.data["companies"]]

    def replace(self, companies: Iterable[Company]) -> None:
        """Overwrite the list (de-duplicated by key, seed entries first)."""
        by_key: dict[str, Company] = {}
        for company in companies:
            by_key.setdefault(company.key, company)
        ordered = sorted(by_key.values(), key=lambda c: (c.source != "seed", c.name.lower()))
        self.data["companies"] = [c.to_dict() for c in ordered]
        self.data["refreshed_at"] = utcnow().isoformat()

    def region_counts(self) -> Counter[str]:
        """How many companies target each region (for logging / digest)."""
        return Counter(r for c in self.all() for r in c.regions)
