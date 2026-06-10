from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from maintainer_radar.models import RepositorySnapshot, WorkItem
from maintainer_radar.scoring import ScoringConfig, rank_findings, score_item

NOW = datetime(2026, 6, 10, 12, tzinfo=UTC)


def item(**changes: object) -> WorkItem:
    base = WorkItem(
        repository="acme/widgets",
        number=1,
        title="Improve widget",
        url="https://github.com/acme/widgets/issues/1",
        author="octo",
        labels=(),
        created_at=NOW - timedelta(days=2),
        updated_at=NOW - timedelta(days=1),
        assignees=("maintainer",),
        kind="issue",
    )
    return replace(base, **changes)


@pytest.mark.parametrize(
    ("changes", "expected_score", "reason_fragment"),
    [
        (
            {"kind": "pull_request", "check_conclusion": "failure"},
            40,
            "failing checks",
        ),
        (
            {"kind": "pull_request", "review_decision": "CHANGES_REQUESTED"},
            30,
            "changes requested",
        ),
        (
            {
                "kind": "pull_request",
                "created_at": NOW - timedelta(days=8),
                "requested_reviewers": ("reviewer",),
            },
            25,
            "waiting 8 days",
        ),
        (
            {
                "kind": "pull_request",
                "review_decision": "APPROVED",
                "check_conclusion": "success",
            },
            20,
            "approved",
        ),
        ({"updated_at": NOW - timedelta(days=31)}, 15, "stale for 31 days"),
        ({"assignees": ()}, 10, "unassigned"),
        ({"labels": ("security",)}, 10, "priority label"),
        ({"kind": "pull_request", "draft": True}, -30, "draft"),
    ],
)
def test_each_scoring_rule(
    changes: dict[str, object], expected_score: int, reason_fragment: str
) -> None:
    finding = score_item(item(**changes), NOW, ScoringConfig())

    assert finding.score == expected_score
    assert any(reason_fragment in reason.lower() for reason in finding.reasons)


def test_rules_are_additive_and_act_now_is_highest_priority() -> None:
    finding = score_item(
        item(
            kind="pull_request",
            labels=("security",),
            check_conclusion="failure",
            review_decision="CHANGES_REQUESTED",
        ),
        NOW,
        ScoringConfig(),
    )

    assert finding.score == 80
    assert finding.category == "act_now"
    assert finding.recommended_action == "Resolve the blocking signals before moving this forward."


def test_approved_green_pull_request_is_ready_to_land() -> None:
    finding = score_item(
        item(
            kind="pull_request",
            review_decision="APPROVED",
            check_conclusion="success",
        ),
        NOW,
        ScoringConfig(),
    )

    assert finding.category == "ready_to_land"
    assert "final maintainer review" in finding.recommended_action.lower()


def test_old_item_without_blockers_is_stale() -> None:
    finding = score_item(
        item(updated_at=NOW - timedelta(days=45)),
        NOW,
        ScoringConfig(stale_days=30),
    )

    assert finding.category == "stale"


def test_rank_findings_sorts_by_score_then_oldest_update_then_number() -> None:
    items = (
        item(number=3, assignees=(), updated_at=NOW - timedelta(days=4)),
        item(number=2, assignees=(), updated_at=NOW - timedelta(days=5)),
        item(number=1, assignees=(), updated_at=NOW - timedelta(days=5)),
        item(number=4, labels=("security", "regression")),
    )
    snapshot = RepositorySnapshot("acme/widgets", NOW, items)

    findings = rank_findings(snapshot, ScoringConfig())

    assert [finding.item.number for finding in findings] == [1, 2, 3, 4]


def test_thresholds_are_configurable() -> None:
    work = item(
        kind="pull_request",
        created_at=NOW - timedelta(days=4),
        updated_at=NOW - timedelta(days=4),
        requested_reviewers=("reviewer",),
    )

    finding = score_item(
        work,
        NOW,
        ScoringConfig(stale_days=3, review_wait_days=3),
    )

    assert finding.score == 40
    assert finding.category == "review_next"
