"""Core domain models shared by sources, classifiers, stores and publishers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

_LEGAL_SUFFIXES = re.compile(
    r"\b(inc|ltd|limited|gmbh|ag|bv|llc|plc|pte|pvt|corp|corporation|co|company|se|sa|nv|oy|ab|"
    r"as|aps|srl|spa|sas|the|technologies|technology|labs)\b"
)


def normalise_name(name: str) -> str:
    """Return a comparison key for a company name.

    Lowercases, strips punctuation and common legal suffixes so that
    ``"Acme GmbH"``, ``"ACME, Inc."`` and ``"acme"`` all collapse to ``"acme"``.

    Args:
        name: Raw company name as it appears in a posting or register.

    Returns:
        Normalised key; may be empty for degenerate input.
    """
    lowered = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    stripped = _LEGAL_SUFFIXES.sub(" ", lowered)
    return " ".join(stripped.split())


@dataclass(frozen=True, slots=True)
class Company:
    """A company believed to sponsor visas or provide relocation support.

    Attributes:
        name: Display name.
        regions: Region keys (see ``settings.regions``) this company hires into.
        ats: Applicant-tracking system exposing a public board API
            (``greenhouse`` | ``lever`` | ``ashby``) or ``None``.
        ats_token: Board slug used by the ATS API.
        careers_url: Human careers page, informational only.
        source: Where the entry came from (``seed`` | ``observed`` | ``manual``).
        verified_by: Names of sponsor registries that list this company.
    """

    name: str
    regions: tuple[str, ...] = ()
    ats: str | None = None
    ats_token: str | None = None
    careers_url: str | None = None
    source: str = "seed"
    verified_by: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        """Normalised name used for de-duplication and registry lookups."""
        return normalise_name(self.name)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Company:
        """Build from a dict produced by :meth:`to_dict` or the seed YAML."""
        return cls(
            name=data["name"],
            regions=tuple(data.get("regions") or ()),
            ats=data.get("ats"),
            ats_token=data.get("ats_token"),
            careers_url=data.get("careers_url"),
            source=data.get("source", "seed"),
            verified_by=tuple(data.get("verified_by") or ()),
        )


@dataclass(slots=True)
class Job:
    """A single job posting normalised across all sources.

    Attributes:
        title: Job title.
        company: Company display name.
        url: Canonical application URL; also the identity of the job.
        location: Free-text location as provided by the source.
        posted_at: Timezone-aware publish time, or ``None`` when unknown.
        source: Name of the :class:`~relocation_agent.sources.base.JobSource`.
        description: Plain-text description (HTML stripped). May be truncated.
        remote: Whether the source marks the role as remote.
        tags: Free-form tags from the source.
        regions: Region keys assigned by the screener.
        signal: Short human-readable reason the job was accepted.
    """

    title: str
    company: str
    url: str
    location: str
    posted_at: datetime | None
    source: str
    description: str = ""
    remote: bool = False
    tags: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()
    signal: str | None = None

    @property
    def id(self) -> str:
        """Stable 16-hex-char identifier derived from the URL."""
        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict (description dropped to keep state small)."""
        data = asdict(self)
        data.pop("description", None)
        data["posted_at"] = self.posted_at.isoformat() if self.posted_at else None
        data["id"] = self.id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        """Rehydrate from :meth:`to_dict` output."""
        posted = data.get("posted_at")
        return cls(
            title=data["title"],
            company=data["company"],
            url=data["url"],
            location=data.get("location", ""),
            posted_at=datetime.fromisoformat(posted) if posted else None,
            source=data.get("source", "unknown"),
            description=data.get("description", ""),
            remote=bool(data.get("remote", False)),
            tags=tuple(data.get("tags") or ()),
            regions=tuple(data.get("regions") or ()),
            signal=data.get("signal"),
        )
