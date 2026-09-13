"""The three entry-point workflows: discover, publish, refresh-companies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from relocation_agent.classify import Screener
from relocation_agent.companies.refresh import RefreshStats, refresh_companies
from relocation_agent.companies.seed import load_seed
from relocation_agent.config import Secrets, Settings
from relocation_agent.digest import write_digest
from relocation_agent.formatting import compose
from relocation_agent.models import Job
from relocation_agent.publisher.base import PublishError
from relocation_agent.publisher.factory import build_publishers
from relocation_agent.sources.registry import build_sources
from relocation_agent.stores import CompanyStore, QueueStore, SeenStore
from relocation_agent.utils import get_logger, utcnow

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DiscoverStats:
    """Summary of one discover run."""

    fetched: int
    new: int
    accepted: int
    queued: int
    llm_calls: int


def run_discover(settings: Settings) -> DiscoverStats:
    """Pull every enabled source, screen new postings and enqueue the accepted ones.

    Idempotent: re-running within the same day adds nothing thanks to
    :class:`SeenStore`.
    """
    now = utcnow()
    since = now - timedelta(hours=settings.publishing.lookback_hours)
    companies = CompanyStore(settings.paths.companies).all() or load_seed(settings.companies.seed_file)
    seen = SeenStore(settings.paths.seen)
    queue = QueueStore(settings.paths.queue)
    screener = Screener(settings.classifier, settings.regions)

    fetched = new = 0
    accepted: list[Job] = []
    for source in build_sources(settings.sources):
        before = fetched
        try:
            for job in source.fetch(since, companies):
                fetched += 1
                if not job.url or not job.title or seen.has(job.id):
                    continue
                if job.posted_at is not None and job.posted_at < since:
                    continue
                new += 1
                screened = screener.screen(job)
                seen.add(job, accepted=screened is not None, now=now)
                if screened:
                    accepted.append(screened)
        except Exception as exc:  # noqa: BLE001 — one source failing must not kill the rest
            log.error("Source %s failed: %s", source.name, exc)
        log.info("%s: fetched=%d", source.name, fetched - before)

    # Sort so freshest go first; queue is FIFO.
    accepted.sort(key=lambda j: j.posted_at or now, reverse=True)
    queued = queue.enqueue(accepted)
    queue.expire(max_age_hours=settings.publishing.lookback_hours * 3)
    seen.prune()
    seen.save()
    queue.save()
    write_digest(queue.data["items"] + queue.recent_history(50), settings.paths.digest_dir)

    stats = DiscoverStats(fetched, new, len(accepted), queued, screener.llm_calls)
    log.info("Discover: %s (queue size now %d)", stats, len(queue))
    return stats


def run_publish(settings: Settings, secrets: Secrets, *, dry_run: bool = False) -> bool:
    """Publish at most one queued job if the cap and spacing allow.

    Designed to be invoked every 15–20 minutes by cron; each invocation is
    cheap and stateless apart from ``data/queue.json``.

    Returns:
        True if a post was made.
    """
    now = utcnow()
    queue = QueueStore(settings.paths.queue)
    pub = settings.publishing
    if not queue.can_post(now, daily_cap=pub.daily_cap, min_gap_minutes=pub.min_gap_minutes):
        log.info("Skip: cap/gap not satisfied (posted today=%d)", queue.posted_today(now))
        return False
    job = queue.peek()
    if job is None:
        log.info("Skip: queue empty")
        return False

    text = compose(job, pub, settings.regions, limit=pub.max_chars)
    receipts: dict[str, str] = {}
    failures = 0
    for publisher in build_publishers(secrets, force_dry_run=dry_run):
        try:
            receipts[publisher.name] = publisher.publish(text, url=job.url)
        except PublishError as exc:
            failures += 1
            log.error("%s: %s", publisher.name, exc)

    if receipts:
        queue.mark_published(job, now=now, receipts=receipts)
    elif failures:
        # Nothing delivered; leave the item so the next tick retries, but don't loop on a poison item.
        queue.drop(job)
        log.error("All publishers failed; dropped %s to avoid blocking the queue", job.url)
    queue.save()
    return bool(receipts)


def run_refresh(settings: Settings) -> RefreshStats:
    """Weekly company-list rebuild (see :mod:`relocation_agent.companies.refresh`)."""
    return refresh_companies(
        settings,
        seen=SeenStore(settings.paths.seen),
        store=CompanyStore(settings.paths.companies),
    )
