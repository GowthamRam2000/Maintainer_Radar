from datetime import UTC, datetime, timedelta

from maintainer_radar.models import RepositorySnapshot, WorkItem
from maintainer_radar.render import DASHBOARD_MARKER, render_report
from maintainer_radar.scoring import ScoringConfig, rank_findings

NOW = datetime(2026, 6, 10, 12, tzinfo=UTC)


def snapshot() -> RepositorySnapshot:
    return RepositorySnapshot(
        repository="acme/widgets",
        generated_at=NOW,
        items=(
            WorkItem(
                repository="acme/widgets",
                number=12,
                title="Fix [parser] <unsafe>",
                url="https://github.com/acme/widgets/issues/12",
                author="octo",
                labels=("security",),
                created_at=NOW - timedelta(days=40),
                updated_at=NOW - timedelta(days=35),
                assignees=(),
                kind="issue",
            ),
            WorkItem(
                repository="acme/widgets",
                number=18,
                title="Release widget v2",
                url="https://github.com/acme/widgets/pull/18",
                author="hubot",
                labels=(),
                created_at=NOW - timedelta(days=5),
                updated_at=NOW - timedelta(days=1),
                assignees=("maintainer",),
                kind="pull_request",
                review_decision="APPROVED",
                check_conclusion="success",
            ),
        ),
    )


def test_report_contains_marker_metrics_sections_and_configuration() -> None:
    data = snapshot()
    config = ScoringConfig(stale_days=30, review_wait_days=7)
    report = render_report(data, rank_findings(data, config), config, max_items=5)

    assert report.startswith(DASHBOARD_MARKER)
    assert "# Maintainer Radar: `acme/widgets`" in report
    assert "| Open issues | 1 |" in report
    assert "| Open pull requests | 1 |" in report
    assert "## Act now" in report
    assert "## Review next" in report
    assert "## Ready to land" in report
    assert "## Stale and unassigned" in report
    assert "stale after **30 days**" in report
    assert "review wait after **7 days**" in report
    assert "Scores prioritize human attention" in report


def test_report_escapes_untrusted_titles_and_explains_scores() -> None:
    data = snapshot()
    config = ScoringConfig()
    report = render_report(data, rank_findings(data, config), config)

    assert "<unsafe>" not in report
    assert "&lt;unsafe&gt;" in report
    assert "\\[parser\\]" in report
    assert "Item has a priority label: security (+10)." in report
    assert "Triage the priority label" in report


def test_report_labels_optional_ai_summary() -> None:
    data = snapshot()
    config = ScoringConfig()
    report = render_report(
        data,
        rank_findings(data, config),
        config,
        ai_summary="Address the security issue before the release pull request.",
    )

    assert "## AI-assisted summary" in report
    assert "Address the security issue" in report
    assert "deterministic findings below remain the source of truth" in report


def test_empty_sections_have_explicit_empty_state() -> None:
    empty = RepositorySnapshot("acme/widgets", NOW, ())
    report = render_report(empty, (), ScoringConfig())

    assert report.count("_No matching items._") == 4


def test_max_items_limits_each_section() -> None:
    data = snapshot()
    config = ScoringConfig()
    findings = rank_findings(data, config)

    report = render_report(data, findings, config, max_items=0)

    assert report.count("_No matching items._") == 4
