from maintainer_radar.github import GitHubClient, GitHubError
from tests.helpers import FakeTransport

API = "https://api.github.com"


def test_get_paginated_follows_link_headers() -> None:
    transport = FakeTransport()
    first = f"{API}/repos/acme/widgets/issues?state=open&per_page=100"
    second = f"{API}/repositories/1/issues?page=2"
    transport.add(
        "GET",
        first,
        [{"number": 1}],
        headers={"Link": f'<{second}>; rel="next"'},
    )
    transport.add("GET", second, [{"number": 2}])
    client = GitHubClient("token", transport=transport)

    result = client.get_paginated("/repos/acme/widgets/issues?state=open&per_page=100")

    assert [entry["number"] for entry in result] == [1, 2]


def test_fetch_snapshot_normalizes_issues_and_enriches_pull_requests() -> None:
    transport = FakeTransport()
    issues_url = f"{API}/repos/acme/widgets/issues?state=open&per_page=100"
    transport.add(
        "GET",
        issues_url,
        [
            {
                "number": 4,
                "title": "Broken widget",
                "html_url": "https://github.com/acme/widgets/issues/4",
                "user": {"login": "octo"},
                "labels": [{"name": "regression"}],
                "created_at": "2026-05-01T08:00:00Z",
                "updated_at": "2026-05-02T08:00:00Z",
                "assignees": [],
                "milestone": None,
            },
            {
                "number": 8,
                "title": "Fix widget",
                "html_url": "https://github.com/acme/widgets/pull/8",
                "user": {"login": "hubot"},
                "labels": [{"name": "security"}],
                "created_at": "2026-06-01T08:00:00Z",
                "updated_at": "2026-06-08T08:00:00Z",
                "assignees": [{"login": "maintainer"}],
                "milestone": {"title": "2.0"},
                "pull_request": {"url": f"{API}/repos/acme/widgets/pulls/8"},
            },
        ],
    )
    transport.add(
        "GET",
        f"{API}/repos/acme/widgets/pulls/8",
        {
            "draft": False,
            "requested_reviewers": [{"login": "reviewer"}],
            "head": {"sha": "abc123"},
        },
    )
    transport.add(
        "GET",
        f"{API}/repos/acme/widgets/pulls/8/reviews?per_page=100",
        [
            {"user": {"login": "reviewer"}, "state": "CHANGES_REQUESTED", "id": 2},
            {"user": {"login": "reviewer"}, "state": "APPROVED", "id": 1},
        ],
    )
    transport.add(
        "GET",
        f"{API}/repos/acme/widgets/commits/abc123/check-runs?per_page=100",
        {"check_runs": [{"name": "test", "conclusion": "failure"}]},
    )
    client = GitHubClient("token", transport=transport)

    snapshot = client.fetch_snapshot("acme/widgets")

    assert len(snapshot.items) == 2
    issue, pull = snapshot.items
    assert issue.kind == "issue"
    assert issue.labels == ("regression",)
    assert pull.kind == "pull_request"
    assert pull.requested_reviewers == ("reviewer",)
    assert pull.review_decision == "CHANGES_REQUESTED"
    assert pull.check_conclusion == "failure"
    assert pull.milestone == "2.0"


def test_authentication_error_has_actionable_message_without_token() -> None:
    transport = FakeTransport()
    url = f"{API}/repos/acme/widgets/issues?state=open&per_page=100"
    transport.add("GET", url, {"message": "Bad credentials"}, status=401)
    client = GitHubClient("super-secret-token", transport=transport)

    try:
        client.fetch_snapshot("acme/widgets")
    except GitHubError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected GitHubError")

    assert "authentication failed" in message.lower()
    assert "super-secret-token" not in message


def test_rate_limit_error_reports_reset_time() -> None:
    transport = FakeTransport()
    url = f"{API}/repos/acme/widgets/issues?state=open&per_page=100"
    transport.add(
        "GET",
        url,
        {"message": "API rate limit exceeded"},
        status=403,
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1781126400"},
    )
    client = GitHubClient("token", transport=transport)

    try:
        client.fetch_snapshot("acme/widgets")
    except GitHubError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected GitHubError")

    assert "rate limit" in message.lower()
    assert "1781126400" in message
