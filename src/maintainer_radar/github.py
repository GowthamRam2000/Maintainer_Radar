from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from maintainer_radar.models import RepositorySnapshot

API_BASE = "https://api.github.com"
Transport = Callable[..., Any]


class GitHubError(RuntimeError):
    """Raised when GitHub data cannot be fetched or changed safely."""


class GitHubClient:
    def __init__(
        self,
        token: str,
        *,
        transport: Transport = urlopen,
        timeout: int = 30,
    ) -> None:
        if not token:
            raise ValueError("A GitHub token is required")
        self._token = token
        self._transport = transport
        self._timeout = timeout

    def get_paginated(self, path_or_url: str) -> list[dict[str, Any]]:
        url: str | None = self._url(path_or_url)
        results: list[dict[str, Any]] = []
        while url:
            payload, headers = self._request(url)
            if not isinstance(payload, list):
                raise GitHubError("GitHub returned an unexpected paginated response")
            results.extend(entry for entry in payload if isinstance(entry, dict))
            url = _next_link(_header(headers, "Link"))
        return results

    def fetch_snapshot(self, repository: str) -> RepositorySnapshot:
        _validate_repository(repository)
        raw_items = self.get_paginated(
            f"/repos/{repository}/issues?state=open&per_page=100"
        )
        items = [self._normalize_item(repository, item) for item in raw_items]
        payload = {
            "repository": repository,
            "generated_at": datetime.now(UTC).isoformat(),
            "items": items,
        }
        return RepositorySnapshot.from_dict(payload)

    def list_open_issues(self, repository: str) -> list[dict[str, Any]]:
        _validate_repository(repository)
        return self.get_paginated(
            f"/repos/{repository}/issues?state=open&per_page=100"
        )

    def create_issue(
        self,
        repository: str,
        *,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        payload, _ = self._request(
            f"/repos/{repository}/issues",
            method="POST",
            payload={"title": title, "body": body, "labels": labels or []},
        )
        return _object(payload, "create issue")

    def update_issue(
        self,
        repository: str,
        number: int,
        *,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        payload, _ = self._request(
            f"/repos/{repository}/issues/{number}",
            method="PATCH",
            payload={"title": title, "body": body},
        )
        return _object(payload, "update issue")

    def _normalize_item(
        self,
        repository: str,
        raw: Mapping[str, Any],
    ) -> dict[str, Any]:
        number = raw.get("number")
        is_pull_request = isinstance(raw.get("pull_request"), Mapping)
        normalized: dict[str, Any] = {
            "number": number,
            "title": raw.get("title"),
            "url": raw.get("html_url"),
            "author": _login(raw.get("user")),
            "labels": [
                str(label["name"])
                for label in raw.get("labels", [])
                if isinstance(label, Mapping) and label.get("name")
            ],
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
            "assignees": [
                login
                for entry in raw.get("assignees", [])
                if (login := _login(entry, required=False))
            ],
            "kind": "pull_request" if is_pull_request else "issue",
            "milestone": _milestone(raw.get("milestone")),
        }
        if not is_pull_request:
            return normalized

        detail, _ = self._request(f"/repos/{repository}/pulls/{number}")
        detail = _object(detail, "fetch pull request")
        reviewers = [
            login
            for entry in detail.get("requested_reviewers", [])
            if (login := _login(entry, required=False))
        ]
        reviews = self.get_paginated(
            f"/repos/{repository}/pulls/{number}/reviews?per_page=100"
        )
        sha = _nested_text(detail, "head", "sha")
        checks, _ = self._request(
            f"/repos/{repository}/commits/{sha}/check-runs?per_page=100"
        )
        checks = _object(checks, "fetch check runs")
        normalized.update(
            {
                "draft": bool(detail.get("draft", False)),
                "requested_reviewers": reviewers,
                "review_decision": _review_decision(reviews),
                "check_conclusion": _check_conclusion(checks.get("check_runs", [])),
            }
        )
        return normalized

    def _request(
        self,
        path_or_url: str,
        *,
        method: str = "GET",
        payload: Mapping[str, Any] | None = None,
    ) -> tuple[Any, Mapping[str, str]]:
        url = self._url(path_or_url)
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "maintainer-radar/0.1.0",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with self._transport(request, timeout=self._timeout) as response:
                status = int(getattr(response, "status", 200))
                headers = getattr(response, "headers", {})
                raw_body = response.read()
                decoded = json.loads(raw_body.decode()) if raw_body else None
                if status >= 400:
                    raise _github_error(status, headers, decoded)
                return decoded, headers
        except HTTPError as exc:
            raw_body = exc.read()
            decoded = json.loads(raw_body.decode()) if raw_body else None
            raise _github_error(exc.code, exc.headers, decoded) from None
        except URLError as exc:
            raise GitHubError(f"Could not reach GitHub: {exc.reason}") from None

    @staticmethod
    def _url(path_or_url: str) -> str:
        return path_or_url if path_or_url.startswith("https://") else f"{API_BASE}{path_or_url}"


def _validate_repository(repository: str) -> None:
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", repository):
        raise ValueError("repository must use the owner/name format")


def _header(headers: Mapping[str, str], name: str) -> str | None:
    direct = headers.get(name)
    if direct is not None:
        return direct
    lower_name = name.lower()
    for key, value in headers.items():
        if key.lower() == lower_name:
            return value
    return None


def _next_link(value: str | None) -> str | None:
    if not value:
        return None
    for part in value.split(","):
        match = re.match(r'\s*<([^>]+)>;\s*rel="([^"]+)"', part)
        if match and match.group(2) == "next":
            return match.group(1)
    return None


def _github_error(
    status: int,
    headers: Mapping[str, str],
    payload: object,
) -> GitHubError:
    if status == 401:
        return GitHubError("GitHub authentication failed; check GITHUB_TOKEN permissions")
    if status == 403 and _header(headers, "X-RateLimit-Remaining") == "0":
        reset = _header(headers, "X-RateLimit-Reset") or "unknown"
        return GitHubError(f"GitHub API rate limit exceeded; reset timestamp: {reset}")
    message = payload.get("message") if isinstance(payload, Mapping) else None
    suffix = f": {message}" if isinstance(message, str) else ""
    return GitHubError(f"GitHub API request failed with status {status}{suffix}")


def _object(value: object, operation: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GitHubError(f"GitHub returned an unexpected response while trying to {operation}")
    return value


def _login(value: object, *, required: bool = True) -> str:
    if isinstance(value, Mapping) and isinstance(value.get("login"), str):
        return str(value["login"])
    if required:
        raise GitHubError("GitHub returned an item without an author login")
    return ""


def _milestone(value: object) -> str | None:
    if isinstance(value, Mapping) and isinstance(value.get("title"), str):
        return str(value["title"])
    return None


def _nested_text(value: Mapping[str, Any], parent: str, child: str) -> str:
    parent_value = value.get(parent)
    if isinstance(parent_value, Mapping) and isinstance(parent_value.get(child), str):
        return str(parent_value[child])
    raise GitHubError(f"GitHub pull request response is missing {parent}.{child}")


def _review_decision(reviews: list[dict[str, Any]]) -> str | None:
    latest_by_user: dict[str, tuple[int, str]] = {}
    for review in reviews:
        user = _login(review.get("user"), required=False)
        state = review.get("state")
        review_id = review.get("id", 0)
        if user and isinstance(state, str) and isinstance(review_id, int):
            latest_by_user[user] = (review_id, state.upper())
    states = {state for _, state in latest_by_user.values()}
    if "CHANGES_REQUESTED" in states:
        return "CHANGES_REQUESTED"
    if "APPROVED" in states:
        return "APPROVED"
    return None


def _check_conclusion(check_runs: object) -> str | None:
    if not isinstance(check_runs, list) or not check_runs:
        return None
    conclusions = {
        str(run.get("conclusion")).lower()
        for run in check_runs
        if isinstance(run, Mapping) and run.get("conclusion")
    }
    for failure in ("failure", "timed_out", "cancelled", "action_required"):
        if failure in conclusions:
            return "failure"
    if conclusions and conclusions <= {"success", "neutral", "skipped"}:
        return "success"
    return "pending"
