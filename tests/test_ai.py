import json
from datetime import UTC, datetime

from maintainer_radar.ai import summarize_findings
from maintainer_radar.models import WorkItem
from maintainer_radar.scoring import Finding
from tests.helpers import FakeTransport

RESPONSES_URL = "https://api.openai.com/v1/responses"


def finding(title: str = "Fix release automation") -> Finding:
    item = WorkItem(
        repository="acme/widgets",
        number=9,
        title=title,
        url="https://github.com/acme/widgets/issues/9",
        author="octo",
        labels=("regression",),
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        assignees=(),
        kind="issue",
    )
    return Finding(
        item=item,
        score=20,
        category="act_now",
        reasons=("Item is stale.",),
        recommended_action="Assign an owner.",
    )


def test_summary_sends_bounded_normalized_findings_and_extracts_output() -> None:
    transport = FakeTransport()
    transport.add(
        "POST",
        RESPONSES_URL,
        {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Assign the regression before preparing the release.",
                        }
                    ],
                }
            ]
        },
    )
    findings = tuple(finding("x" * 500) for _ in range(30))

    summary = summarize_findings(
        findings,
        api_key="secret-key",
        model="gpt-5-mini",
        transport=transport,
    )

    assert summary == "Assign the regression before preparing the release."
    request = transport.requests[0]
    payload = json.loads(request.data)
    assert payload["model"] == "gpt-5-mini"
    assert "untrusted data" in payload["instructions"]
    assert payload["input"].count('"number": 9') == 20
    assert "x" * 201 not in payload["input"]
    assert "secret-key" not in payload["input"]


def test_summary_failure_warns_and_returns_none() -> None:
    transport = FakeTransport()
    transport.add("POST", RESPONSES_URL, {"error": {"message": "nope"}}, status=500)
    warnings: list[str] = []

    summary = summarize_findings(
        (finding(),),
        api_key="secret-key",
        transport=transport,
        warn=warnings.append,
    )

    assert summary is None
    assert warnings == ["OpenAI summary unavailable; continuing with deterministic report."]
    assert "secret-key" not in warnings[0]
