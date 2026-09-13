"""Command-line interface: ``relocation-agent {discover|publish|refresh-companies}``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from relocation_agent import pipeline
from relocation_agent.config import Secrets, Settings
from relocation_agent.utils import get_logger

log = get_logger("relocation_agent")


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser (exposed for docs/tests)."""
    parser = argparse.ArgumentParser(prog="relocation-agent", description=__doc__)
    parser.add_argument("--settings", type=Path, default=Path("config/settings.yaml"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("discover", help="fetch, screen and enqueue new postings (daily)")
    publish = sub.add_parser("publish", help="post the next queued job if allowed (every 15–20 min)")
    publish.add_argument("--dry-run", action="store_true", help="log instead of posting")
    sub.add_parser("refresh-companies", help="rebuild the company list (weekly)")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    settings = Settings.load(args.settings)
    if args.command == "discover":
        pipeline.run_discover(settings)
    elif args.command == "publish":
        pipeline.run_publish(settings, Secrets.from_env(), dry_run=args.dry_run)
    elif args.command == "refresh-companies":
        pipeline.run_refresh(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
