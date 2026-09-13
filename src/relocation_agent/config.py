"""Typed configuration: ``settings.yaml`` (behaviour) and environment (secrets)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class RegionConfig(BaseModel):
    """How to detect a region from a location string and how to hashtag it."""

    keywords: list[str]
    hashtags: list[str] = Field(default_factory=list)
    emoji: str = "🌍"
    requires_remote: bool = False


class LLMConfig(BaseModel):
    """Optional LLM verification for postings the rules can't decide."""

    enabled: bool = False
    model: str = "claude-haiku-4-5-20251001"
    max_calls_per_run: int = 40
    description_chars: int = 3000


class ClassifierConfig(BaseModel):
    """Rule patterns plus LLM fallback."""

    positive_patterns: list[str]
    negative_patterns: list[str]
    llm: LLMConfig = Field(default_factory=LLMConfig)


class PublishingConfig(BaseModel):
    """Posting cadence, caps and message shape."""

    daily_cap: int = 10
    min_gap_minutes: int = 15
    lookback_hours: int = 24
    link_mode: Literal["none", "url"] = "url"
    no_link_text: str = "🔗 See digest for the apply link"
    max_title_chars: int = 90
    max_chars: int = 1000
    template: str
    digest_url: str | None = None


class RegistryConfig(BaseModel):
    """A government sponsor register used to verify companies."""

    enabled: bool = True
    url: str | None = None
    dataset_id: str | None = None
    route_filter: str | None = None


class CompaniesConfig(BaseModel):
    """Company list maintenance."""

    seed_file: Path
    observed_window_days: int = 7
    probe_ats: bool = True
    max_probes_per_run: int = 40
    registries: dict[str, RegistryConfig] = Field(default_factory=dict)


class PathsConfig(BaseModel):
    """Where mutable state is persisted (committed back to the repo by CI)."""

    companies: Path
    seen: Path
    queue: Path
    digest_dir: Path = Path("docs")


class Settings(BaseModel):
    """Root of ``settings.yaml``."""

    regions: dict[str, RegionConfig]
    sources: dict[str, dict[str, Any]]
    classifier: ClassifierConfig
    publishing: PublishingConfig
    companies: CompaniesConfig
    paths: PathsConfig

    @field_validator("regions")
    @classmethod
    def _non_empty(cls, value: dict[str, RegionConfig]) -> dict[str, RegionConfig]:
        if not value:
            raise ValueError("at least one region must be configured")
        return value

    @classmethod
    def load(cls, path: Path | str = "config/settings.yaml") -> Settings:
        """Parse and validate a YAML settings file.

        Args:
            path: Path to ``settings.yaml``.

        Returns:
            Validated settings.

        Raises:
            FileNotFoundError: If the file is missing.
            pydantic.ValidationError: If the content is malformed.
        """
        with Path(path).open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        return cls.model_validate(raw)


class Secrets(BaseModel):
    """Credentials read from environment variables (never from YAML)."""

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    anthropic_api_key: str | None = None
    publishers: list[str] = Field(default_factory=lambda: ["dryrun"])

    @classmethod
    def from_env(cls) -> Secrets:
        """Read secrets from the process environment."""
        env = os.environ
        publishers = [p.strip() for p in env.get("PUBLISHERS", "dryrun").split(",") if p.strip()]
        return cls(
            telegram_bot_token=env.get("TELEGRAM_BOT_TOKEN") or None,
            telegram_chat_id=env.get("TELEGRAM_CHAT_ID") or None,
            anthropic_api_key=env.get("ANTHROPIC_API_KEY") or None,
            publishers=publishers,
        )

    @property
    def has_telegram(self) -> bool:
        """True when bot token and chat id are present."""
        return bool(self.telegram_bot_token and self.telegram_chat_id)
