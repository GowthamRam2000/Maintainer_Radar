from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any
from urllib.request import Request


@dataclass
class FakeResponse:
    payload: Any
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeTransport:
    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], deque[FakeResponse]] = defaultdict(deque)
        self.requests: list[Request] = []

    def add(
        self,
        method: str,
        url: str,
        payload: Any,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.routes[(method, url)].append(
            FakeResponse(payload=payload, status=status, headers=headers or {})
        )

    def __call__(self, request: Request, timeout: int = 30) -> FakeResponse:
        del timeout
        self.requests.append(request)
        key = (request.get_method(), request.full_url)
        if not self.routes[key]:
            raise AssertionError(f"Unexpected request: {key}")
        return self.routes[key].popleft()
