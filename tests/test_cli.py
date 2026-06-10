from __future__ import annotations

from io import StringIO
from pathlib import Path

from maintainer_radar.cli import run
from maintainer_radar.models import RepositorySnapshot
from maintainer_radar.publish import Publication

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "examples" / "demo-repository.json"


def load_snapshot() -> RepositorySnapshot:
    import json

    return RepositorySnapshot.from_dict(json.loads(FIXTURE.read_text()))


class FakeGitHubClient:
    def __init__(self, token: str) -> None:
        assert token == "token"

    def fetch_snapshot(self, repository: str) -> RepositorySnapshot:
        assert repository == "acme/launchpad"
        return load_snapshot()


def test_fixture_mode_prints_deterministic_report() -> None:
    stdout = StringIO()
    stderr = StringIO()

    code = run(
        ["scan", "--fixture", str(FIXTURE)],
        environ={},
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 0
    assert "# Maintainer Radar: `acme/launchpad`" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_output_file_is_written(tmp_path: Path) -> None:
    output = tmp_path / "report.md"

    code = run(
        ["scan", "--fixture", str(FIXTURE), "--output", str(output)],
        environ={},
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert code == 0
    assert output.read_text().startswith("<!-- maintainer-radar-dashboard -->")


def test_invalid_repository_returns_configuration_error() -> None:
    stderr = StringIO()

    code = run(
        ["scan", "--repo", "not-a-repository"],
        environ={"GITHUB_TOKEN": "token"},
        stdout=StringIO(),
        stderr=stderr,
        github_factory=FakeGitHubClient,
    )

    assert code == 2
    assert "owner/name" in stderr.getvalue()


def test_live_mode_requires_github_token() -> None:
    stderr = StringIO()

    code = run(
        ["scan", "--repo", "acme/launchpad"],
        environ={},
        stdout=StringIO(),
        stderr=stderr,
    )

    assert code == 1
    assert "GITHUB_TOKEN" in stderr.getvalue()


def test_publish_uses_generated_report_and_reports_result() -> None:
    calls: list[tuple[str, str, str]] = []

    def publisher(
        client: FakeGitHubClient,
        repository: str,
        title: str,
        body: str,
    ) -> Publication:
        assert isinstance(client, FakeGitHubClient)
        calls.append((repository, title, body))
        return Publication(
            action="updated",
            number=22,
            url="https://github.com/acme/launchpad/issues/22",
        )

    stdout = StringIO()
    code = run(
        ["scan", "--repo", "acme/launchpad", "--publish"],
        environ={"GITHUB_TOKEN": "token"},
        stdout=stdout,
        stderr=StringIO(),
        github_factory=FakeGitHubClient,
        publisher=publisher,
    )

    assert code == 0
    assert calls[0][0] == "acme/launchpad"
    assert calls[0][2].startswith("<!-- maintainer-radar-dashboard -->")
    assert "updated dashboard issue #22" in stdout.getvalue().lower()


def test_fixture_cannot_be_published() -> None:
    stderr = StringIO()

    code = run(
        ["scan", "--fixture", str(FIXTURE), "--publish"],
        environ={},
        stdout=StringIO(),
        stderr=stderr,
    )

    assert code == 2
    assert "fixture" in stderr.getvalue().lower()
