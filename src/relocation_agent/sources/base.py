"""Contract every job source implements."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from relocation_agent.models import Company, Job


@runtime_checkable
class JobSource(Protocol):
    """A provider of :class:`~relocation_agent.models.Job` objects.

    Implementations must be side-effect free, must not raise for a single bad
    record, and should stop paginating once records are older than ``since``.
    """

    name: str

    def fetch(self, since: datetime, companies: Sequence[Company]) -> Iterable[Job]:
        """Yield jobs published at or after ``since``.

        Args:
            since: Aware UTC lower bound on ``posted_at``.
            companies: Current company list; sources that poll company boards
                use it, aggregator sources may ignore it.
        """
        ...
