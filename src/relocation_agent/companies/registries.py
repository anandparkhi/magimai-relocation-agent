"""Official sponsor registers used to *verify* (not discover) companies.

- UK: Home Office "Register of licensed sponsors: workers" (CSV, ~100k rows).
- Canada: ESDC "Positive LMIA employers" open dataset (CSV via CKAN).

Both are large, so they are loaded once per refresh and queried by
normalised name. Neither says a company is *hiring*; they say it *can* sponsor.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Protocol

from relocation_agent.config import RegistryConfig
from relocation_agent.models import normalise_name
from relocation_agent.utils import get_json, get_logger, http_get

log = get_logger(__name__)


class SponsorRegistry(Protocol):
    """A loadable set of sponsor names."""

    name: str

    def load(self) -> None:
        """Download and index the register. Idempotent."""
        ...

    def contains(self, company_name: str) -> bool:
        """Whether a company with this (normalised) name is listed."""
        ...


def _index_csv(text: str, *, name_column: str, predicate=None) -> set[str]:  # type: ignore[no-untyped-def]
    reader = csv.DictReader(io.StringIO(text))
    columns = reader.fieldnames or []
    column = next((c for c in columns if name_column.lower() in c.lower()), None)
    if column is None:
        raise ValueError(f"no column matching {name_column!r} in {columns}")
    names: set[str] = set()
    for row in reader:
        if predicate and not predicate(row):
            continue
        key = normalise_name(row.get(column) or "")
        if key:
            names.add(key)
    return names


class UKSponsorRegister:
    """UK Skilled Worker sponsor register."""

    name = "uk_sponsor_register"

    def __init__(self, config: RegistryConfig) -> None:
        self._page_url = config.url or ""
        self._route_filter = config.route_filter
        self._names: set[str] | None = None

    def load(self) -> None:
        """Find the current CSV link on the gov.uk page and index organisation names."""
        if self._names is not None:
            return
        page = http_get(self._page_url).text
        match = re.search(r'https://assets\.publishing\.service\.gov\.uk/[^"\']+\.csv', page)
        if not match:
            raise ValueError("could not locate CSV link on UK register page")
        text = http_get(match.group(0), timeout=120).text
        route = self._route_filter

        def keep(row: dict[str, str]) -> bool:
            return not route or route.lower() in (row.get("Route") or "").lower()

        self._names = _index_csv(text, name_column="organisation", predicate=keep)
        log.info("UK register loaded: %d sponsors", len(self._names))

    def contains(self, company_name: str) -> bool:
        """See :class:`SponsorRegistry`."""
        return bool(self._names) and normalise_name(company_name) in self._names  # type: ignore[operator]


class CanadaLMIARegistry:
    """Employers with a positive LMIA (Temporary Foreign Worker Program)."""

    name = "canada_lmia"

    def __init__(self, config: RegistryConfig) -> None:
        self._dataset_id = config.dataset_id or ""
        self._names: set[str] | None = None

    def load(self) -> None:
        """Pick the newest CSV resource from the CKAN package and index employer names."""
        if self._names is not None:
            return
        meta = get_json(
            "https://open.canada.ca/data/api/action/package_show",
            params={"id": self._dataset_id},
        )
        resources = [
            r
            for r in meta.get("result", {}).get("resources", [])
            if (r.get("format") or "").upper() == "CSV" and r.get("url")
        ]
        if not resources:
            raise ValueError("no CSV resources in LMIA dataset")
        newest = max(resources, key=lambda r: r.get("created") or r.get("name") or "")
        text = http_get(newest["url"], timeout=120).text
        self._names = _index_csv(text, name_column="employer")
        log.info("Canada LMIA registry loaded: %d employers", len(self._names))

    def contains(self, company_name: str) -> bool:
        """See :class:`SponsorRegistry`."""
        return bool(self._names) and normalise_name(company_name) in self._names  # type: ignore[operator]


REGISTRY_FACTORIES = {
    "uk_sponsor_register": UKSponsorRegister,
    "canada_lmia": CanadaLMIARegistry,
}


def build_registries(config: dict[str, RegistryConfig]) -> list[SponsorRegistry]:
    """Instantiate enabled registries from settings."""
    return [
        REGISTRY_FACTORIES[name](cfg)  # type: ignore[abstract]
        for name, cfg in config.items()
        if cfg.enabled and name in REGISTRY_FACTORIES
    ]
