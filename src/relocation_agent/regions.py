"""Map free-text locations to configured region keys."""

from __future__ import annotations

import re
from collections.abc import Mapping

from relocation_agent.config import RegionConfig


def _compile(keywords: list[str]) -> re.Pattern[str]:
    escaped = [re.escape(k.lower()) for k in keywords]
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(escaped) + r")(?![a-z0-9])")


class RegionDetector:
    """Detects which configured regions a location string refers to.

    Matching is word-bounded so that ``"us"`` does not match ``"Austin"`` and
    ``"uk"`` does not match ``"Ukraine"``.
    """

    def __init__(self, regions: Mapping[str, RegionConfig]) -> None:
        self._regions = dict(regions)
        self._patterns = {name: _compile(cfg.keywords) for name, cfg in regions.items()}

    def detect(self, location: str, *, remote: bool = False) -> tuple[str, ...]:
        """Return region keys whose keywords appear in ``location``.

        Args:
            location: Free-text location from the posting.
            remote: Whether the posting is remote; regions with
                ``requires_remote`` are only returned when this is true.
        """
        haystack = (location or "").lower()
        hits: list[str] = []
        for name, pattern in self._patterns.items():
            if self._regions[name].requires_remote and not remote:
                continue
            if pattern.search(haystack):
                hits.append(name)
        return tuple(hits)
