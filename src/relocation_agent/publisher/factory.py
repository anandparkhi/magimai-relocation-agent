"""Build the publisher list from ``PUBLISHERS`` plus available credentials."""

from __future__ import annotations

from relocation_agent.config import Secrets
from relocation_agent.publisher.base import Publisher
from relocation_agent.publisher.dryrun import DryRunPublisher
from relocation_agent.publisher.telegram import TelegramPublisher
from relocation_agent.utils import get_logger

log = get_logger(__name__)


def build_publishers(secrets: Secrets, *, force_dry_run: bool = False) -> list[Publisher]:
    """Instantiate publishers named in ``secrets.publishers`` whose credentials exist.

    Falls back to :class:`DryRunPublisher` when nothing usable is configured or
    ``force_dry_run`` is set, so a misconfigured environment never crashes CI.
    """
    if force_dry_run:
        return [DryRunPublisher()]
    publishers: list[Publisher] = []
    for name in secrets.publishers:
        if name == "telegram" and secrets.has_telegram:
            publishers.append(
                TelegramPublisher(secrets.telegram_bot_token, secrets.telegram_chat_id)  # type: ignore[arg-type]
            )
        elif name == "dryrun":
            publishers.append(DryRunPublisher())
        else:
            log.warning("Publisher %r requested but credentials missing — skipped", name)
    return publishers or [DryRunPublisher()]
