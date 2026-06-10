from datetime import UTC, datetime

import pytest

from maintainer_radar.models import DataValidationError, RepositorySnapshot


def valid_payload() -> dict:
    return {
        "repository": "acme/widgets",
        "generated_at": "2026-06-10T12:00:00Z",
        "items": [
            {
                "number": 12,
                "title": "Fix <script>alert(1)</script> parser",
                "url": "https://github.com/acme/widgets/issues/12",
                "author": "octo",
                "labels": ["regression"],
                "created_at": "2026-05-01T08:00:00Z",
                "updated_at": "2026-05-02T08:00:00Z",
                "assignees": [],
                "kind": "issue",
            },
            {
                "number": 18,
                "title": "Ship widget v2",
                "url": "https://github.com/acme/widgets/pull/18",
                "author": "hubot",
                "labels": ["release-blocker"],
                "created_at": "2026-06-01T08:00:00+00:00",
                "updated_at": "2026-06-08T08:00:00+00:00",
                "assignees": ["maintainer"],
                "kind": "pull_request",
                "draft": False,
                "requested_reviewers": ["reviewer"],
                "review_decision": "CHANGES_REQUESTED",
                "check_conclusion": "failure",
                "milestone": "2.0",
            },
        ],
    }


def test_snapshot_parses_normalized_items() -> None:
    snapshot = RepositorySnapshot.from_dict(valid_payload())

    assert snapshot.repository == "acme/widgets"
    assert snapshot.generated_at == datetime(2026, 6, 10, 12, tzinfo=UTC)
    assert snapshot.items[0].kind == "issue"
    assert snapshot.items[0].title == "Fix alert(1) parser"
    assert snapshot.items[1].kind == "pull_request"
    assert snapshot.items[1].requested_reviewers == ("reviewer",)
    assert snapshot.items[1].review_decision == "CHANGES_REQUESTED"


@pytest.mark.parametrize("repository", ["", "widgets", "acme/", "/widgets", "a/b/c"])
def test_snapshot_rejects_invalid_repository(repository: str) -> None:
    payload = valid_payload()
    payload["repository"] = repository

    with pytest.raises(DataValidationError, match="repository"):
        RepositorySnapshot.from_dict(payload)


def test_snapshot_identifies_invalid_item_field() -> None:
    payload = valid_payload()
    del payload["items"][0]["updated_at"]

    with pytest.raises(DataValidationError, match="items\\[0\\].updated_at"):
        RepositorySnapshot.from_dict(payload)


def test_snapshot_rejects_unknown_kind() -> None:
    payload = valid_payload()
    payload["items"][0]["kind"] = "discussion"

    with pytest.raises(DataValidationError, match="items\\[0\\].kind"):
        RepositorySnapshot.from_dict(payload)
