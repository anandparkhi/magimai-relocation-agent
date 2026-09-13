"""Name → constructor mapping so sources can be toggled purely from YAML."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from relocation_agent.sources.arbeitnow import ArbeitnowSource
from relocation_agent.sources.ats import ATSSource
from relocation_agent.sources.base import JobSource
from relocation_agent.sources.jobicy import JobicySource
from relocation_agent.sources.remotive import RemotiveSource

SOURCE_FACTORIES: dict[str, Callable[..., JobSource]] = {
    "arbeitnow": ArbeitnowSource,
    "remotive": RemotiveSource,
    "jobicy": JobicySource,
    "ats": ATSSource,
}


def build_sources(config: Mapping[str, Mapping[str, Any]]) -> list[JobSource]:
    """Instantiate every enabled source from the ``sources`` section of settings.

    Each section's keys (minus ``enabled``) are passed as constructor kwargs, so
    adding a new option to a source needs no code change here.

    Raises:
        KeyError: If the YAML names a source that is not registered.
    """
    sources: list[JobSource] = []
    for name, options in config.items():
        opts = dict(options)
        if not opts.pop("enabled", True):
            continue
        factory = SOURCE_FACTORIES[name]
        sources.append(factory(**opts))
    return sources
