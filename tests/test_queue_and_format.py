"""Queue rate limiting and post composition."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from relocation_agent.config import Settings
from relocation_agent.formatting import compose, weighted_length
from relocation_agent.models import Job
from relocation_agent.stores import QueueStore


def test_queue_cap_and_gap(tmp_path: Path, job: Job) -> None:
    queue = QueueStore(tmp_path / "q.json")
    jobs = [replace(job, url=f"https://x.test/{i}") for i in range(12)]
    assert queue.enqueue(jobs) == 12
    assert queue.enqueue(jobs) == 0  # idempotent
    now = datetime(2026, 9, 13, 9, 0, tzinfo=UTC)
    posted = 0
    for tick in range(30):
        t = now + timedelta(minutes=20 * tick)
        if queue.can_post(t, daily_cap=10, min_gap_minutes=15) and (j := queue.peek()):
            queue.mark_published(j, now=t, receipts={"dryrun": "x"})
            posted += 1
    assert posted == 10
    assert len(queue) == 2
    # Gap enforced: 5 minutes after the last post is too soon.
    last = datetime.fromisoformat(queue.data["last_posted_at"])
    assert not queue.can_post(last + timedelta(minutes=5), daily_cap=100, min_gap_minutes=15)
    assert queue.can_post(last + timedelta(minutes=16), daily_cap=100, min_gap_minutes=15)


def test_compose_fits_limit_with_long_title(settings: Settings, job: Job) -> None:
    job.title = "Staff Software Engineer, Distributed Systems & Platform Reliability (Java/Kotlin/Go)" * 2
    job.regions = ("europe", "canada", "remote_us")
    cfg = settings.publishing.model_copy(update={"link_mode": "none"})
    text = compose(job, cfg, settings.regions, limit=280)
    assert weighted_length(text, None) <= 280
    assert settings.publishing.no_link_text in text


def test_compose_url_mode_weights_link(settings: Settings, job: Job) -> None:
    cfg = settings.publishing.model_copy(update={"link_mode": "url"})
    job.url = "https://boards.greenhouse.io/very/long/path/that/would/otherwise/blow/the/limit/" + "x" * 120
    text = compose(job, cfg, settings.regions, limit=280)
    assert job.url in text
    assert weighted_length(text, job.url) <= 280
