"""Shared fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from relocation_agent.config import Settings
from relocation_agent.models import Job


@pytest.fixture(scope="session")
def settings() -> Settings:
    """The real settings file — tests double as config validation."""
    return Settings.load("config/settings.yaml")


@pytest.fixture
def job() -> Job:
    """A plausible accepted posting."""
    return Job(
        title="Senior Backend Engineer (Java)",
        company="Acme GmbH",
        url="https://example.com/jobs/123",
        location="Berlin, Germany",
        posted_at=datetime(2026, 9, 13, 8, 0, tzinfo=UTC),
        source="test",
        description="We offer visa sponsorship and a relocation package to Berlin.",
        regions=("europe",),
        signal="Visa sponsorship",
    )
