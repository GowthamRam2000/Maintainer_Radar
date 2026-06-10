from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from maintainer_radar.models import RepositorySnapshot, WorkItem

FindingCategory = Literal["act_now", "review_next", "ready_to_land", "stale"]
PRIORITY_LABELS = frozenset({"security", "regression", "release-blocker"})
FAILING_CHECKS = frozenset({"failure", "failed", "error", "timed_out", "cancelled"})


@dataclass(frozen=True, slots=True)
class ScoringConfig:
    stale_days: int = 30
    review_wait_days: int = 7

    def __post_init__(self) -> None:
        if self.stale_days < 1:
            raise ValueError("stale_days must be at least 1")
        if self.review_wait_days < 1:
            raise ValueError("review_wait_days must be at least 1")


@dataclass(frozen=True, slots=True)
class Finding:
    item: WorkItem
    score: int
    category: FindingCategory
    reasons: tuple[str, ...]
    recommended_action: str


def score_item(item: WorkItem, now: datetime, config: ScoringConfig) -> Finding:
    score = 0
    reasons: list[str] = []
    labels = {label.lower() for label in item.labels}
    check = (item.check_conclusion or "").lower()
    review = (item.review_decision or "").upper()
    age_days = max(0, (now - item.created_at).days)
    stale_days = max(0, (now - item.updated_at).days)

    has_failing_checks = item.kind == "pull_request" and check in FAILING_CHECKS
    has_changes_requested = item.kind == "pull_request" and review == "CHANGES_REQUESTED"
    waiting_for_review = (
        item.kind == "pull_request"
        and not item.draft
        and review not in {"APPROVED", "CHANGES_REQUESTED"}
        and bool(item.requested_reviewers)
        and age_days >= config.review_wait_days
    )
    ready_to_land = (
        item.kind == "pull_request"
        and not item.draft
        and review == "APPROVED"
        and check in {"success", "neutral", "skipped"}
    )
    is_stale = stale_days >= config.stale_days
    has_priority_label = bool(labels & PRIORITY_LABELS)

    if has_failing_checks:
        score += 40
        reasons.append("Pull request has failing checks (+40).")
    if has_changes_requested:
        score += 30
        reasons.append("Review has changes requested (+30).")
    if waiting_for_review:
        score += 25
        reasons.append(f"Pull request has been waiting {age_days} days for review (+25).")
    if ready_to_land:
        score += 20
        reasons.append("Pull request is approved and checks are passing (+20).")
    if is_stale:
        score += 15
        reasons.append(f"Item has been stale for {stale_days} days (+15).")
    if not item.assignees:
        score += 10
        reasons.append("Item is unassigned (+10).")
    if has_priority_label:
        matched = ", ".join(sorted(labels & PRIORITY_LABELS))
        score += 10
        reasons.append(f"Item has a priority label: {matched} (+10).")
    if item.kind == "pull_request" and item.draft:
        score -= 30
        reasons.append("Pull request is still a draft (-30).")

    if has_failing_checks or has_changes_requested:
        category: FindingCategory = "act_now"
        action = "Resolve the blocking signals before moving this forward."
    elif ready_to_land:
        category = "ready_to_land"
        action = "Perform a final maintainer review and merge when appropriate."
    elif waiting_for_review:
        category = "review_next"
        action = "Assign or complete the requested review."
    elif has_priority_label:
        category = "act_now"
        action = "Triage the priority label and assign a clear owner."
    elif is_stale:
        category = "stale"
        action = "Confirm whether this is still relevant, then update or close it."
    else:
        category = "review_next"
        action = "Review the item and define its next owner or milestone."

    if not reasons:
        reasons.append("No urgency rule matched; included for queue visibility.")

    return Finding(
        item=item,
        score=score,
        category=category,
        reasons=tuple(reasons),
        recommended_action=action,
    )


def rank_findings(
    snapshot: RepositorySnapshot,
    config: ScoringConfig,
) -> tuple[Finding, ...]:
    findings = [score_item(item, snapshot.generated_at, config) for item in snapshot.items]
    return tuple(
        sorted(
            findings,
            key=lambda finding: (
                -finding.score,
                finding.item.updated_at,
                finding.item.number,
            ),
        )
    )
