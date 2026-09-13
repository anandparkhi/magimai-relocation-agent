"""Turn a :class:`Job` into a post that fits platform limits."""

from __future__ import annotations

from relocation_agent.config import PublishingConfig, RegionConfig
from relocation_agent.models import Job

DEFAULT_LIMIT = 1000
URL_WEIGHT = 23  # some platforms count a URL as a fixed width; keeps posts portable


def weighted_length(text: str, url: str | None) -> int:
    """Length with the URL counted at a fixed weight regardless of its real length."""
    if url and url in text:
        return len(text) - len(url) + URL_WEIGHT
    return len(text)


def compose(
    job: Job, config: PublishingConfig, regions: dict[str, RegionConfig], *, limit: int = DEFAULT_LIMIT
) -> str:
    """Render the configured template for ``job`` and squeeze it under ``limit``.

    Trimming order: title (to ``max_title_chars``), then hashtags one by one,
    then the location. The link line is never trimmed.

    Args:
        job: Screened job (must have ``regions``).
        config: ``publishing`` settings.
        regions: ``regions`` settings for emoji and hashtags.
        limit: Character limit of the target platform.
    """
    primary = regions.get(job.regions[0]) if job.regions else None
    emoji = primary.emoji if primary else "🌍"
    hashtags: list[str] = []
    for key in job.regions:
        for tag in regions[key].hashtags:
            if tag not in hashtags:
                hashtags.append(tag)

    link = job.url if config.link_mode == "url" else config.no_link_text
    url_for_weight = job.url if config.link_mode == "url" else None
    title = _shorten(job.title, config.max_title_chars)
    location = job.location or "Remote"

    def render(tags: list[str], loc: str) -> str:
        text = config.template.format(
            emoji=emoji,
            company=job.company,
            title=title,
            location=loc,
            signal=job.signal or "Relocation / visa support mentioned",
            link=link,
            hashtags=" ".join(tags),
        )
        return "\n".join(line.rstrip() for line in text.splitlines() if line.strip())

    text = render(hashtags, location)
    while weighted_length(text, url_for_weight) > limit and hashtags:
        hashtags.pop()
        text = render(hashtags, location)
    if weighted_length(text, url_for_weight) > limit:
        text = render(hashtags, _shorten(location, 30))
    if weighted_length(text, url_for_weight) > limit:  # last resort: hard cut, keep link intact
        overflow = weighted_length(text, url_for_weight) - limit
        title = _shorten(title, max(10, len(title) - overflow - 1))
        text = render(hashtags, _shorten(location, 30))
    return text


def _shorten(text: str, max_chars: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"
