"""Rule classifier and screener behaviour."""

from __future__ import annotations

from relocation_agent.classify import RuleClassifier, Screener, Verdict, _head_and_tail, _parse_llm
from relocation_agent.config import Settings
from relocation_agent.models import Job


def _job(description: str, location: str = "Berlin, Germany", remote: bool = False) -> Job:
    return Job("Engineer", "Acme", "https://x.test/1", location, None, "t", description, remote)


def _no_llm(settings: Settings):  # type: ignore[no-untyped-def]
    llm = settings.classifier.llm.model_copy(update={"enabled": False})
    return settings.classifier.model_copy(update={"llm": llm})


def test_negative_beats_positive(settings: Settings) -> None:
    rules = RuleClassifier(settings.classifier.positive_patterns, settings.classifier.negative_patterns)
    verdict = rules.classify(_job("Great relocation package. Note: no visa sponsorship."))
    assert verdict.verdict is Verdict.REJECT


def test_positive_match(settings: Settings) -> None:
    rules = RuleClassifier(settings.classifier.positive_patterns, settings.classifier.negative_patterns)
    decision = rules.classify(_job("We offer relocation assistance and Blue Card support."))
    assert decision.verdict is Verdict.ACCEPT
    assert decision.signal


def test_screener_requires_region(settings: Settings) -> None:
    cfg = _no_llm(settings)
    screener = Screener(cfg, settings.regions)
    assert screener.screen(_job("visa sponsorship available", location="Pune, India")) is None
    accepted = screener.screen(_job("visa sponsorship available", location="Amsterdam, NL"))
    assert accepted is not None and accepted.regions == ("europe",)


def test_remote_us_requires_remote_flag(settings: Settings) -> None:
    cfg = _no_llm(settings)
    screener = Screener(cfg, settings.regions)
    assert screener.screen(_job("we sponsor visas", location="Worldwide", remote=False)) is None
    assert screener.screen(_job("we sponsor visas", location="Worldwide", remote=True)) is not None


def test_llm_json_parsing_tolerates_fences() -> None:
    raw = '```json\n{"relocation_support": true, "regions": ["europe","mars"], "reason": "explicit"}\n```'
    decision = _parse_llm(raw, allowed=["europe"])
    assert decision.verdict is Verdict.ACCEPT
    assert decision.regions == ("europe",)


def test_no_trigger_word_is_rejected_without_llm(settings: Settings) -> None:
    cfg = settings.classifier
    rules = RuleClassifier(cfg.positive_patterns, cfg.negative_patterns, cfg.llm_trigger_patterns)
    assert rules.classify(_job("Account executive, quota carrying, remote USA.")).verdict is Verdict.REJECT
    assert rules.classify(_job("We help international hires with their visa.")).verdict is Verdict.UNSURE


def test_negative_phrasings(settings: Settings) -> None:
    rules = RuleClassifier(settings.classifier.positive_patterns, settings.classifier.negative_patterns)
    for text in [
        "Visa sponsorship is not offered for this role.",
        "Please note that we do not offer visa sponsorship.",
        "We are not able to provide visa sponsorship at this time.",
        "This role is not eligible for visa sponsorship.",
        "Candidates must already hold the right to work in Germany.",
        "Unfortunately we are unable to sponsor work visas.",
        "We are not currently sponsoring visas.",
        "Work permit sponsorship is unavailable.",
    ]:
        assert rules.classify(_job(text)).verdict is Verdict.REJECT, text


def test_source_flag_cannot_override_negative(settings: Settings) -> None:
    screener = Screener(_no_llm(settings), settings.regions)
    flagged = _job("Visa sponsorship is not offered.", location="Berlin, Germany")
    flagged.signal = "Visa sponsorship (flagged by Arbeitnow)"
    assert screener.screen(flagged) is None


def test_llm_input_keeps_the_tail() -> None:
    text = "A" * 5000 + " Visa sponsorship is not offered."
    trimmed = _head_and_tail(text, 3000)
    assert trimmed.endswith("Visa sponsorship is not offered.")
    assert len(trimmed) <= 3000 + len("\n[...]\n")
