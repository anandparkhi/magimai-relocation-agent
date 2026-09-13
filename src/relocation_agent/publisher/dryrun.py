"""Publisher that only logs — the default until real credentials are supplied."""

from __future__ import annotations

from relocation_agent.utils import get_logger

log = get_logger(__name__)


class DryRunPublisher:
    """Prints the post instead of sending it."""

    name = "dryrun"

    def publish(self, text: str, *, url: str | None = None) -> str:
        """Log the message and return a fake receipt."""
        log.info("DRY RUN post (%d chars)%s:\n%s", len(text), f" [{url}]" if url else "", text)
        return "dry-run"
