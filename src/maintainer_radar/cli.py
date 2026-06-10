from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TextIO

from maintainer_radar.ai import summarize_findings
from maintainer_radar.github import GitHubClient, GitHubError
from maintainer_radar.models import DataValidationError, RepositorySnapshot
from maintainer_radar.publish import Publication, publish_dashboard
from maintainer_radar.render import render_report
from maintainer_radar.scoring import Finding, ScoringConfig, rank_findings

GitHubFactory = Callable[[str], GitHubClient]
Publisher = Callable[[GitHubClient, str, str, str], Publication]
AISummarizer = Callable[..., str | None]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maintainer-radar",
        description="Turn a GitHub maintenance queue into a prioritized Markdown digest.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan", help="Generate a maintenance digest")
    source = scan.add_mutually_exclusive_group(required=True)
    source.add_argument("--repo", metavar="OWNER/REPO")
    source.add_argument("--fixture", type=Path, metavar="PATH")
    scan.add_argument("--stale-days", type=int, default=30)
    scan.add_argument("--review-wait-days", type=int, default=7)
    scan.add_argument("--max-items", type=int, default=10)
    scan.add_argument("--output", type=Path)
    scan.add_argument("--publish", action="store_true")
    scan.add_argument("--dashboard-title", default="Maintainer Radar dashboard")
    scan.add_argument("--ai-summary", action="store_true")
    scan.add_argument("--openai-model", default="gpt-5-mini")
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    github_factory: GitHubFactory = GitHubClient,
    publisher: Publisher = publish_dashboard,
    ai_summarizer: AISummarizer = summarize_findings,
) -> int:
    environ = os.environ if environ is None else environ
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    if args.repo and not re.fullmatch(r"[^/\s]+/[^/\s]+", args.repo):
        print("error: repository must use the owner/name format", file=stderr)
        return 2
    if args.fixture and args.publish:
        print("error: a fixture report cannot be published to GitHub", file=stderr)
        return 2

    try:
        config = ScoringConfig(
            stale_days=args.stale_days,
            review_wait_days=args.review_wait_days,
        )
        client: GitHubClient | None = None
        if args.fixture:
            snapshot = _load_fixture(args.fixture)
        else:
            token = environ.get("GITHUB_TOKEN", "")
            if not token:
                print("error: GITHUB_TOKEN is required for live repository scans", file=stderr)
                return 1
            client = github_factory(token)
            snapshot = client.fetch_snapshot(args.repo)

        findings = rank_findings(snapshot, config)
        ai_summary = _maybe_summarize(
            findings,
            enabled=args.ai_summary,
            api_key=environ.get("OPENAI_API_KEY"),
            model=args.openai_model,
            summarizer=ai_summarizer,
            stderr=stderr,
        )
        report = render_report(
            snapshot,
            findings,
            config,
            max_items=args.max_items,
            ai_summary=ai_summary,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
            print(f"Wrote report to {args.output}", file=stdout)
        else:
            print(report, file=stdout)

        if args.publish:
            if client is None:
                print("error: publishing requires a live repository scan", file=stderr)
                return 2
            publication = publisher(
                client,
                snapshot.repository,
                args.dashboard_title,
                report,
            )
            print(
                (
                    f"{publication.action.title()} dashboard issue "
                    f"#{publication.number}: {publication.url}"
                ),
                file=stdout,
            )
        return 0
    except (DataValidationError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=stderr)
        return 2
    except (GitHubError, OSError) as exc:
        print(f"error: {exc}", file=stderr)
        return 1


def main() -> int:
    return run()


def _load_fixture(path: Path) -> RepositorySnapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DataValidationError("fixture root must be an object")
    return RepositorySnapshot.from_dict(payload)


def _maybe_summarize(
    findings: Sequence[Finding],
    *,
    enabled: bool,
    api_key: str | None,
    model: str,
    summarizer: AISummarizer,
    stderr: TextIO,
) -> str | None:
    if not enabled:
        return None
    if not api_key:
        print(
            "warning: OPENAI_API_KEY is not set; using deterministic report only",
            file=stderr,
        )
        return None
    return summarizer(
        findings,
        api_key=api_key,
        model=model,
        warn=lambda message: print(f"warning: {message}", file=stderr),
    )
