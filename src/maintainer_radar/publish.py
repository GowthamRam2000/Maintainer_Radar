from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from maintainer_radar.github import GitHubClient, GitHubError
from maintainer_radar.render import DASHBOARD_MARKER


@dataclass(frozen=True, slots=True)
class Publication:
    action: Literal["created", "updated"]
    number: int
    url: str


def publish_dashboard(
    client: GitHubClient,
    repository: str,
    title: str,
    body: str,
) -> Publication:
    if DASHBOARD_MARKER not in body:
        raise ValueError("dashboard body is missing its stable marker")

    existing = next(
        (
            issue
            for issue in client.list_open_issues(repository)
            if isinstance(issue.get("body"), str) and DASHBOARD_MARKER in issue["body"]
        ),
        None,
    )
    if existing:
        number = _number(existing)
        result = client.update_issue(repository, number, title=title, body=body)
        action: Literal["created", "updated"] = "updated"
    else:
        result = client.create_issue(
            repository,
            title=title,
            body=body,
            labels=["maintainer-radar"],
        )
        number = _number(result)
        action = "created"

    url = result.get("html_url")
    if not isinstance(url, str):
        raise GitHubError("GitHub issue response is missing html_url")
    return Publication(action=action, number=number, url=url)


def _number(issue: dict[str, object]) -> int:
    number = issue.get("number")
    if not isinstance(number, int):
        raise GitHubError("GitHub issue response is missing a numeric issue number")
    return number
