"""Weekly company-list refresh.

seed ∪ observed (companies that posted accepted jobs recently)
→ probe missing ATS boards → verify against sponsor registries → save.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from relocation_agent.companies.ats_probe import probe
from relocation_agent.companies.registries import build_registries
from relocation_agent.companies.seed import load_seed
from relocation_agent.config import Settings
from relocation_agent.models import Company
from relocation_agent.stores import CompanyStore, SeenStore
from relocation_agent.utils import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RefreshStats:
    """Summary of one refresh run."""

    total: int
    observed_added: int
    ats_probed: int
    ats_found: int
    verified: int


def refresh_companies(settings: Settings, *, seen: SeenStore, store: CompanyStore) -> RefreshStats:
    """Rebuild ``data/companies.json``. Returns run statistics."""
    cfg = settings.companies
    seed = load_seed(cfg.seed_file)
    existing = {c.key: c for c in store.all()}
    merged: dict[str, Company] = {c.key: c for c in seed}

    # Keep previously observed companies (and their probed ATS info).
    for key, company in existing.items():
        if key not in merged:
            merged[key] = company

    # Add companies observed posting accepted jobs recently.
    observed_added = 0
    for name, regions in seen.accepted_companies(cfg.observed_window_days).items():
        company = Company(name=name, regions=tuple(sorted(regions)), source="observed")
        if company.key and company.key not in merged:
            merged[company.key] = company
            observed_added += 1
        elif company.key in merged:
            current = merged[company.key]
            merged[company.key] = replace(current, regions=tuple(sorted(set(current.regions) | regions)))

    # Probe ATS boards for companies that lack one (bounded per run).
    probed = found = 0
    if cfg.probe_ats:
        for key, company in list(merged.items()):
            if company.ats or probed >= cfg.max_probes_per_run:
                continue
            probed += 1
            hit = probe(company.name)
            if hit:
                found += 1
                merged[key] = replace(company, ats=hit[0], ats_token=hit[1])

    # Verify against official registers.
    verified = 0
    for registry in build_registries(cfg.registries):
        try:
            registry.load()
        except Exception as exc:  # noqa: BLE001 — a registry outage must not block refresh
            log.warning("Registry %s unavailable: %s", registry.name, exc)
            continue
        for key, company in list(merged.items()):
            if registry.contains(company.name) and registry.name not in company.verified_by:
                merged[key] = replace(company, verified_by=(*company.verified_by, registry.name))
                verified += 1

    store.replace(merged.values())
    store.save()
    stats = RefreshStats(len(merged), observed_added, probed, found, verified)
    log.info("Company refresh: %s", stats)
    return stats
