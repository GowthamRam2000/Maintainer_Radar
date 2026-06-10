from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Mapping

ItemKind = Literal["issue", "pull_request"]


class DataValidationError(ValueError):
    """Raised when repository data cannot be normalized safely."""


@dataclass(frozen=True, slots=True)
class WorkItem:
    repository: str
    number: int
    title: str
    url: str
    author: str
    labels: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    assignees: tuple[str, ...]
    kind: ItemKind
    draft: bool = False
    requested_reviewers: tuple[str, ...] = ()
    review_decision: str | None = None
    check_conclusion: str | None = None
    milestone: str | None = None


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    repository: str
    generated_at: datetime
    items: tuple[WorkItem, ...]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RepositorySnapshot:
        repository = _repository(payload.get("repository"))
        generated_at = _timestamp(payload.get("generated_at"), "generated_at")
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise DataValidationError("items must be a list")
        items = tuple(_item(repository, value, index) for index, value in enumerate(raw_items))
        return cls(repository=repository, generated_at=generated_at, items=items)


def _repository(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[^/\s]+/[^/\s]+", value):
        raise DataValidationError("repository must use the owner/name format")
    return value


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise DataValidationError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataValidationError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise DataValidationError(f"{field} must include a timezone")
    return parsed


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataValidationError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DataValidationError(f"{field} must be a list of strings")
    return tuple(item.strip() for item in value if item.strip())


def _safe_title(value: object, field: str) -> str:
    title = _text(value, field)
    title = re.sub(r"<[^>]*>", "", title)
    return html.unescape(title).strip()


def _item(repository: str, value: object, index: int) -> WorkItem:
    prefix = f"items[{index}]"
    if not isinstance(value, Mapping):
        raise DataValidationError(f"{prefix} must be an object")

    try:
        number = value["number"]
        title = value["title"]
        url = value["url"]
        author = value["author"]
        labels = value["labels"]
        created_at = value["created_at"]
        updated_at = value["updated_at"]
        assignees = value["assignees"]
        kind = value["kind"]
    except KeyError as exc:
        raise DataValidationError(f"{prefix}.{exc.args[0]} is required") from exc

    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        raise DataValidationError(f"{prefix}.number must be a positive integer")
    if kind not in ("issue", "pull_request"):
        raise DataValidationError(f"{prefix}.kind must be issue or pull_request")

    return WorkItem(
        repository=repository,
        number=number,
        title=_safe_title(title, f"{prefix}.title"),
        url=_text(url, f"{prefix}.url"),
        author=_text(author, f"{prefix}.author"),
        labels=_strings(labels, f"{prefix}.labels"),
        created_at=_timestamp(created_at, f"{prefix}.created_at"),
        updated_at=_timestamp(updated_at, f"{prefix}.updated_at"),
        assignees=_strings(assignees, f"{prefix}.assignees"),
        kind=kind,
        draft=bool(value.get("draft", False)),
        requested_reviewers=_strings(
            value.get("requested_reviewers", []), f"{prefix}.requested_reviewers"
        ),
        review_decision=_optional_text(
            value.get("review_decision"), f"{prefix}.review_decision"
        ),
        check_conclusion=_optional_text(
            value.get("check_conclusion"), f"{prefix}.check_conclusion"
        ),
        milestone=_optional_text(value.get("milestone"), f"{prefix}.milestone"),
    )
