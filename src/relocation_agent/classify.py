"""Decide whether a posting offers visa sponsorship / relocation support.

Two layers:

1. :class:`RuleClassifier` — cheap regex pass. Negative phrases win. Decides
   the clear cases for free.
2. :class:`LLMClassifier` — optional, bounded-cost model call for the
   ambiguous remainder. Returns strict JSON so parsing is deterministic.

:class:`Screener` composes both plus region detection into one ``screen()``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from relocation_agent.config import ClassifierConfig, LLMConfig, RegionConfig
from relocation_agent.models import Job
from relocation_agent.regions import RegionDetector
from relocation_agent.utils import get_logger

log = get_logger(__name__)


class Verdict(StrEnum):
    """Outcome of a classification step."""

    ACCEPT = "accept"
    REJECT = "reject"
    UNSURE = "unsure"


@dataclass(frozen=True, slots=True)
class Decision:
    """A verdict plus the evidence that produced it."""

    verdict: Verdict
    signal: str | None = None
    regions: tuple[str, ...] = ()


class RuleClassifier:
    """Regex-based first pass. Deterministic, zero cost.

    ``trigger`` patterns gate the LLM: a posting that matches neither a positive
    nor a negative pattern *and* contains no trigger word is REJECTED outright
    rather than left UNSURE, because a posting that never mentions visas or
    relocation cannot be offering them. This keeps model calls for the cases
    where wording is genuinely ambiguous.
    """

    def __init__(self, positive: Iterable[str], negative: Iterable[str], trigger: Iterable[str] = ()) -> None:
        self._positive = [re.compile(p, re.IGNORECASE) for p in positive]
        self._negative = [re.compile(p, re.IGNORECASE) for p in negative]
        self._trigger = [re.compile(p, re.IGNORECASE) for p in trigger]

    def classify(self, job: Job) -> Decision:
        """Return ACCEPT/REJECT when a pattern matches, UNSURE otherwise."""
        text = f"{job.title}\n{job.description}"
        for pattern in self._negative:
            if match := pattern.search(text):
                return Decision(Verdict.REJECT, f"negative: {match.group(0)!r}")
        for pattern in self._positive:
            if match := pattern.search(text):
                return Decision(Verdict.ACCEPT, _tidy(match.group(0)))
        if self._trigger and not any(p.search(text) for p in self._trigger):
            return Decision(Verdict.REJECT, "no relocation/visa mention")
        return Decision(Verdict.UNSURE)


_PROMPT = """You screen job postings for candidates in India who need the employer to \
sponsor a work visa or provide relocation support to move to the destination.

Respond with ONLY a JSON object, no prose, no markdown fences:
{{"relocation_support": true|false, "regions": [...], "reason": "<= 12 words"}}

"relocation_support" is true only if the posting explicitly states visa sponsorship, work-permit \
sponsorship, or relocation assistance is available. Silence means false.
"regions" must be a subset of {regions}; use the posting location. \
Use "remote_us" only for remote roles open to candidates outside the US (worldwide/anywhere).

Title: {title}
Company: {company}
Location: {location}
Remote: {remote}
Description (truncated):
{description}
"""


class LLMClassifier:
    """Bounded-cost model verification for postings the rules can't decide.

    The call budget (``max_calls_per_run``) is enforced here so a burst of
    postings can never produce a surprise bill.
    """

    def __init__(self, config: LLMConfig, region_names: Iterable[str]) -> None:
        self._config = config
        self._regions = sorted(region_names)
        self._calls = 0
        self._client = None  # created lazily so tests never need the SDK/key

    @property
    def calls_made(self) -> int:
        """Number of model calls performed so far in this process."""
        return self._calls

    def _get_client(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            import anthropic  # local import: optional dependency at runtime

            self._client = anthropic.Anthropic()
        return self._client

    def classify(self, job: Job) -> Decision:
        """Ask the model; returns UNSURE if the budget is spent or the call fails."""
        if self._calls >= self._config.max_calls_per_run:
            return Decision(Verdict.UNSURE, "llm budget exhausted")
        self._calls += 1
        prompt = _PROMPT.format(
            regions=json.dumps(self._regions),
            title=job.title,
            company=job.company,
            location=job.location,
            remote=job.remote,
            description=job.description[: self._config.description_chars],
        )
        try:
            response = self._get_client().messages.create(
                model=self._config.model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(getattr(block, "text", "") for block in response.content)
            return _parse_llm(text, allowed=self._regions)
        except Exception as exc:  # noqa: BLE001 — never let the LLM break the pipeline
            log.warning("LLM classification failed for %s: %s", job.url, exc)
            return Decision(Verdict.UNSURE, "llm error")


def _parse_llm(text: str, *, allowed: list[str]) -> Decision:
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return Decision(Verdict.UNSURE, "llm returned non-json")
    supported = bool(data.get("relocation_support"))
    regions = tuple(r for r in data.get("regions") or () if r in allowed)
    reason = str(data.get("reason") or "").strip()[:80]
    if supported:
        return Decision(Verdict.ACCEPT, f"LLM: {reason}" if reason else "LLM verified", regions)
    return Decision(Verdict.REJECT, f"LLM: {reason}", regions)


def _tidy(fragment: str) -> str:
    fragment = " ".join(fragment.split())
    return fragment[:1].upper() + fragment[1:]


class Screener:
    """Composes rules → LLM → region detection into a single accept/reject decision."""

    def __init__(self, config: ClassifierConfig, regions: dict[str, RegionConfig]) -> None:
        self._rules = RuleClassifier(
            config.positive_patterns, config.negative_patterns, config.llm_trigger_patterns
        )
        self._detector = RegionDetector(regions)
        self._llm = LLMClassifier(config.llm, regions.keys()) if config.llm.enabled else None

    @property
    def llm_calls(self) -> int:
        """Model calls made so far (0 when the LLM is disabled)."""
        return self._llm.calls_made if self._llm else 0

    def screen(self, job: Job) -> Job | None:
        """Return the job with ``signal`` and ``regions`` filled, or ``None`` to drop it.

        A job is accepted when (a) the source pre-flagged it, or (b) rules say
        ACCEPT, or (c) rules are UNSURE and the LLM says ACCEPT — and in all
        cases at least one region could be assigned.
        """
        decision = Decision(Verdict.ACCEPT, job.signal) if job.signal else self._rules.classify(job)
        if decision.verdict is Verdict.UNSURE and self._llm:
            decision = self._llm.classify(job)
        if decision.verdict is not Verdict.ACCEPT:
            return None
        regions = self._detector.detect(job.location, remote=job.remote) or decision.regions
        if not regions:
            return None
        job.signal = decision.signal or "Relocation / visa support mentioned"
        job.regions = regions
        return job
