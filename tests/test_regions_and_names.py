"""Region detection edge cases and company-name normalisation."""

from __future__ import annotations

from relocation_agent.config import Settings
from relocation_agent.models import normalise_name
from relocation_agent.regions import RegionDetector


def test_word_boundaries(settings: Settings) -> None:
    detector = RegionDetector(settings.regions)
    assert detector.detect("Austin, TX") == ()  # "us" must not match inside "Austin"
    assert detector.detect("Kyiv, Ukraine") == ()  # "uk" must not match inside "Ukraine"
    assert "europe" in detector.detect("London, UK")
    assert "uae" in detector.detect("Dubai, UAE")
    assert "canada" in detector.detect("Toronto, ON, Canada")


def test_normalise_name() -> None:
    assert normalise_name("Acme GmbH") == normalise_name("ACME, Inc.") == "acme"
    assert normalise_name("The Widget Company Ltd") == "widget"
