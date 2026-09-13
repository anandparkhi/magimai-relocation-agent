"""Render a static digest page (GitHub Pages) so posts can say "link in bio".

Output: ``<digest_dir>/index.html`` and ``<digest_dir>/jobs.json``.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from relocation_agent.utils import utcnow

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Visa-sponsored & relocation jobs — daily digest</title>
<style>
 body{{font:16px/1.5 system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#222}}
 h1{{font-size:1.5rem}} .meta{{color:#666;font-size:.9rem}}
 li{{margin:.8rem 0;padding:.6rem;border:1px solid #eee;border-radius:8px}}
 .tag{{display:inline-block;font-size:.75rem;background:#eef;padding:.1rem .4rem;
   border-radius:4px;margin-right:.3rem}}
</style></head><body>
<h1>Visa-sponsored &amp; relocation-supported jobs</h1>
<p class="meta">Updated {updated} UTC · {count} openings from the last few days ·
generated automatically,
always verify sponsorship terms on the employer's page.</p>
<ul>{items}</ul>
</body></html>
"""

_ITEM = """<li><strong>{company}</strong> —
<a href="{url}" rel="noopener" target="_blank">{title}</a><br>
<span class="meta">📍 {location} · {signal}</span><br>{tags}</li>"""


def write_digest(entries: list[dict[str, Any]], out_dir: Path) -> Path:
    """Write ``index.html`` and ``jobs.json`` for the given queue/history entries.

    Args:
        entries: Job dicts (queued first, then recently published).
        out_dir: Directory served by GitHub Pages (usually ``docs/``).

    Returns:
        Path of the HTML file written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    items = "\n".join(
        _ITEM.format(
            company=html.escape(e.get("company", "")),
            url=html.escape(e.get("url", "")),
            title=html.escape(e.get("title", "")),
            location=html.escape(e.get("location", "") or "Remote"),
            signal=html.escape(e.get("signal", "") or ""),
            tags="".join(f'<span class="tag">{html.escape(r)}</span>' for r in e.get("regions", [])),
        )
        for e in entries
    )
    page = _PAGE.format(updated=utcnow().strftime("%Y-%m-%d %H:%M"), count=len(entries), items=items)
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    (out_dir / "jobs.json").write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_dir / "index.html"
