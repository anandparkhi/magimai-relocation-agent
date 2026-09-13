"""Load the hand-curated seed list."""

from __future__ import annotations

from pathlib import Path

import yaml

from relocation_agent.models import Company


def load_seed(path: Path) -> list[Company]:
    """Parse ``companies.seed.yaml`` into models (``source`` forced to ``seed``)."""
    with Path(path).open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return [Company.from_dict({**c, "source": "seed"}) for c in raw.get("companies") or []]
