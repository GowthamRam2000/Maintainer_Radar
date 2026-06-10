import json

from maintainer_radar.github import GitHubClient
from maintainer_radar.publish import publish_dashboard
from maintainer_radar.render import DASHBOARD_MARKER
from tests.helpers import FakeTransport

API = "https://api.github.com"


def test_publish_updates_existing_marker_issue() -> None:
    transport = FakeTransport()
    list_url = f"{API}/repos/acme/widgets/issues?state=open&per_page=100"
    transport.add(
        "GET",
        list_url,
        [
            {
                "number": 42,
                "body": f"{DASHBOARD_MARKER}\nOld report",
                "html_url": "https://github.com/acme/widgets/issues/42",
            }
        ],
    )
    patch_url = f"{API}/repos/acme/widgets/issues/42"
    transport.add(
        "PATCH",
        patch_url,
        {
            "number": 42,
            "html_url": "https://github.com/acme/widgets/issues/42",
        },
    )
    client = GitHubClient("token", transport=transport)

    publication = publish_dashboard(
        client,
        "acme/widgets",
        "Maintenance dashboard",
        f"{DASHBOARD_MARKER}\nNew report",
    )

    assert publication.action == "updated"
    assert publication.number == 42
    request = transport.requests[-1]
    assert json.loads(request.data)["body"].endswith("New report")


def test_publish_creates_dashboard_when_marker_is_absent() -> None:
    transport = FakeTransport()
    list_url = f"{API}/repos/acme/widgets/issues?state=open&per_page=100"
    transport.add("GET", list_url, [])
    create_url = f"{API}/repos/acme/widgets/issues"
    transport.add(
        "POST",
        create_url,
        {
            "number": 7,
            "html_url": "https://github.com/acme/widgets/issues/7",
        },
        status=201,
    )
    client = GitHubClient("token", transport=transport)

    publication = publish_dashboard(
        client,
        "acme/widgets",
        "Maintenance dashboard",
        f"{DASHBOARD_MARKER}\nReport",
    )

    assert publication.action == "created"
    assert publication.number == 7
    request = transport.requests[-1]
    payload = json.loads(request.data)
    assert payload["labels"] == ["maintainer-radar"]
