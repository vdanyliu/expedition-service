import queue
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from expedition_service.back.app import create_app
from expedition_service.back.platform.config import Settings


def build_test_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path.as_posix()}/test.db",
        jwt_secret_key="test-secret",
        jwt_algorithm="HS256",
        access_token_expire_minutes=120,
        websocket_cleanup_interval_seconds=30,
    )


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(build_test_settings(tmp_path))
    with TestClient(app) as test_client:
        yield test_client


def register_user(client: TestClient, email: str, role: str = "member") -> dict[str, Any]:
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "name": email.split("@", maxsplit=1)[0],
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_login_requires_email_field(client: TestClient):
    registered_user = register_user(client, "member@example.com")

    response = client.post("/auth/login", json={"email": "member@example.com"})

    assert response.status_code == 200, response.text
    assert response.json()["access_token"]
    assert response.json()["user"]["id"] == registered_user["user"]["id"]

    wrong_field_response = client.post("/auth/login", json={"username": "member@example.com"})
    assert wrong_field_response.status_code == 422


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_expedition(client: TestClient, token: str, capacity: int = 2) -> dict[str, Any]:
    response = client.post(
        "/expeditions",
        headers=auth_headers(token),
        json={
            "title": "North Ridge",
            "description": "Integration test expedition",
            "capacity": capacity,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def invite_member(client: TestClient, token: str, expedition_id: int, user_id: int):
    return client.post(
        f"/expeditions/{expedition_id}/members/invite",
        headers=auth_headers(token),
        json={"user_id": user_id},
    )


def confirm_membership(client: TestClient, token: str, expedition_id: int):
    return client.post(
        f"/expeditions/{expedition_id}/members/confirm",
        headers=auth_headers(token),
    )


def update_status(client: TestClient, token: str, expedition_id: int, status: str):
    return client.patch(
        f"/expeditions/{expedition_id}/status",
        headers=auth_headers(token),
        json={"status": status},
    )


def create_confirmed_member(client: TestClient, chief_token: str, expedition_id: int, email: str) -> dict[str, Any]:
    member = register_user(client, email)
    invite_response = invite_member(client, chief_token, expedition_id, member["user"]["id"])
    assert invite_response.status_code == 200, invite_response.text
    confirm_response = confirm_membership(client, member["access_token"], expedition_id)
    assert confirm_response.status_code == 200, confirm_response.text
    assert confirm_response.json()["state"] == "confirmed"
    return member


def create_invited_member(client: TestClient, chief_token: str, expedition_id: int, email: str) -> dict[str, Any]:
    member = register_user(client, email)
    invite_response = invite_member(client, chief_token, expedition_id, member["user"]["id"])
    assert invite_response.status_code == 200, invite_response.text
    assert invite_response.json()["state"] == "invited"
    return member


def create_expedition_in_status(
    client: TestClient,
    chief_token: str,
    status: str,
) -> dict[str, Any]:
    expedition = create_expedition(client, chief_token, capacity=2)
    if status == "draft":
        return expedition

    create_confirmed_member(client, chief_token, expedition["id"], "member-1@example.com")
    create_confirmed_member(client, chief_token, expedition["id"], "member-2@example.com")
    ready_response = update_status(client, chief_token, expedition["id"], "ready")
    assert ready_response.status_code == 200, ready_response.text
    if status == "ready":
        return ready_response.json()

    active_response = update_status(client, chief_token, expedition["id"], "active")
    assert active_response.status_code == 200, active_response.text
    if status == "active":
        return active_response.json()

    finished_response = update_status(client, chief_token, expedition["id"], "finished")
    assert finished_response.status_code == 200, finished_response.text
    return finished_response.json()


def start_expedition_with_members(
    client: TestClient,
    chief_token: str,
    expedition_id: int,
    member_tokens: list[str],
) -> None:
    for token in member_tokens:
        confirm_response = confirm_membership(client, token, expedition_id)
        assert confirm_response.status_code == 200, confirm_response.text

    ready_response = update_status(client, chief_token, expedition_id, "ready")
    assert ready_response.status_code == 200, ready_response.text
    active_response = update_status(client, chief_token, expedition_id, "active")
    assert active_response.status_code == 200, active_response.text
    assert active_response.json()["status"] == "active"


def test_expedition_lifecycle_allows_only_ordered_status_transitions(client: TestClient):
    chief = register_user(client, "chief@example.com", "chief")
    expedition = create_expedition(client, chief["access_token"], capacity=2)

    assert expedition["status"] == "draft"
    assert expedition["end_at"] is None

    first_member = create_confirmed_member(client, chief["access_token"], expedition["id"], "member-1@example.com")
    second_member = create_confirmed_member(client, chief["access_token"], expedition["id"], "member-2@example.com")

    ready_response = update_status(client, chief["access_token"], expedition["id"], "ready")
    assert ready_response.status_code == 200, ready_response.text
    assert ready_response.json()["status"] == "ready"

    confirm_again_response = confirm_membership(client, first_member["access_token"], expedition["id"])
    assert confirm_again_response.status_code == 400

    active_response = update_status(client, chief["access_token"], expedition["id"], "active")
    assert active_response.status_code == 200, active_response.text
    assert active_response.json()["status"] == "active"

    ready_again_response = update_status(client, chief["access_token"], expedition["id"], "ready")
    assert ready_again_response.status_code == 400

    finished_response = update_status(client, chief["access_token"], expedition["id"], "finished")
    assert finished_response.status_code == 200, finished_response.text
    assert finished_response.json()["status"] == "finished"
    assert finished_response.json()["end_at"] is not None

    active_again_response = update_status(client, chief["access_token"], expedition["id"], "active")
    assert active_again_response.status_code == 400
    final_ready_response = update_status(client, chief["access_token"], expedition["id"], "ready")
    assert final_ready_response.status_code == 400

    members_response = client.get(
        f"/expeditions/{expedition['id']}/members",
        headers=auth_headers(chief["access_token"]),
    )
    assert members_response.status_code == 200, members_response.text
    assert {member["user_id"] for member in members_response.json()} == {
        first_member["user"]["id"],
        second_member["user"]["id"],
    }


def test_only_expedition_chief_can_update_status(client: TestClient):
    chief = register_user(client, "chief@example.com", "chief")
    member = register_user(client, "member@example.com")
    expedition = create_expedition(client, chief["access_token"])

    response = update_status(client, member["access_token"], expedition["id"], "ready")

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("current_status", "requested_status", "expected_status_code", "expected_status"),
    [
        ("draft", "draft", 400, None),
        ("draft", "ready", 200, "ready"),
        ("draft", "active", 400, None),
        ("draft", "finished", 400, None),
        ("ready", "draft", 400, None),
        ("ready", "ready", 400, None),
        ("ready", "active", 200, "active"),
        ("ready", "finished", 400, None),
        ("active", "draft", 400, None),
        ("active", "ready", 400, None),
        ("active", "active", 400, None),
        ("active", "finished", 200, "finished"),
        ("finished", "draft", 400, None),
        ("finished", "ready", 400, None),
        ("finished", "active", 400, None),
        ("finished", "finished", 400, None),
    ],
)
def test_status_transition_matrix(
    client: TestClient,
    current_status: str,
    requested_status: str,
    expected_status_code: int,
    expected_status: str | None,
):
    chief = register_user(client, "chief@example.com", "chief")
    expedition = create_expedition_in_status(client, chief["access_token"], current_status)

    response = update_status(client, chief["access_token"], expedition["id"], requested_status)

    assert response.status_code == expected_status_code
    if expected_status is not None:
        assert response.json()["status"] == expected_status


def test_activation_requires_at_least_two_confirmed_members(client: TestClient):
    chief = register_user(client, "chief@example.com", "chief")
    expedition = create_expedition(client, chief["access_token"], capacity=2)
    single_member = create_confirmed_member(client, chief["access_token"], expedition["id"], "member-1@example.com")

    members_response = client.get(
        f"/expeditions/{expedition['id']}/members",
        headers=auth_headers(chief["access_token"]),
    )
    assert members_response.status_code == 200, members_response.text
    members = members_response.json()
    assert len(members) == 1
    assert members[0]["user_id"] == single_member["user"]["id"]
    assert members[0]["state"] == "confirmed"

    ready_response = update_status(client, chief["access_token"], expedition["id"], "ready")
    assert ready_response.status_code == 200, ready_response.text

    active_response = update_status(client, chief["access_token"], expedition["id"], "active")

    assert active_response.status_code == 400
    assert active_response.json()["detail"] == "Expedition requires at least two confirmed members"


def test_activation_requires_confirmed_members_not_only_invitations(client: TestClient):
    chief = register_user(client, "chief@example.com", "chief")
    expedition = create_expedition(client, chief["access_token"], capacity=2)
    confirmed_member = create_confirmed_member(client, chief["access_token"], expedition["id"], "member-1@example.com")
    invited_member = create_invited_member(client, chief["access_token"], expedition["id"], "member-2@example.com")

    ready_response = update_status(client, chief["access_token"], expedition["id"], "ready")
    assert ready_response.status_code == 200, ready_response.text

    active_response = update_status(client, chief["access_token"], expedition["id"], "active")

    assert active_response.status_code == 400
    assert active_response.json()["detail"] == "Expedition requires at least two confirmed members"

    members_response = client.get(
        f"/expeditions/{expedition['id']}/members",
        headers=auth_headers(chief["access_token"]),
    )
    assert members_response.status_code == 200, members_response.text
    assert {
        member["user_id"]: member["state"]
        for member in members_response.json()
    } == {
        confirmed_member["user"]["id"]: "confirmed",
        invited_member["user"]["id"]: "invited",
    }


def test_invitations_can_exceed_capacity_before_activation(client: TestClient):
    chief = register_user(client, "chief@example.com", "chief")
    first_member = register_user(client, "member-1@example.com")
    second_member = register_user(client, "member-2@example.com")
    expedition = create_expedition(client, chief["access_token"], capacity=1)

    first_invite_response = invite_member(client, chief["access_token"], expedition["id"], first_member["user"]["id"])
    assert first_invite_response.status_code == 200, first_invite_response.text
    assert first_invite_response.json()["state"] == "invited"

    second_invite_response = invite_member(client, chief["access_token"], expedition["id"], second_member["user"]["id"])
    assert second_invite_response.status_code == 200, second_invite_response.text
    assert second_invite_response.json()["state"] == "invited"

    members_response = client.get(
        f"/expeditions/{expedition['id']}/members",
        headers=auth_headers(chief["access_token"]),
    )
    assert members_response.status_code == 200, members_response.text
    members = members_response.json()
    assert len(members) == 2
    assert {member["state"] for member in members} == {"invited"}


def test_activation_rejects_confirmed_members_over_capacity(client: TestClient):
    chief = register_user(client, "chief@example.com", "chief")
    expedition = create_expedition(client, chief["access_token"], capacity=1)
    first_member = create_confirmed_member(client, chief["access_token"], expedition["id"], "member-1@example.com")
    second_member = create_confirmed_member(client, chief["access_token"], expedition["id"], "member-2@example.com")

    members_response = client.get(
        f"/expeditions/{expedition['id']}/members",
        headers=auth_headers(chief["access_token"]),
    )
    assert members_response.status_code == 200, members_response.text
    members = members_response.json()
    assert {member["user_id"] for member in members} == {
        first_member["user"]["id"],
        second_member["user"]["id"],
    }
    assert {member["state"] for member in members} == {"confirmed"}

    ready_response = update_status(client, chief["access_token"], expedition["id"], "ready")
    assert ready_response.status_code == 200, ready_response.text

    active_response = update_status(client, chief["access_token"], expedition["id"], "active")

    assert active_response.status_code == 400
    assert active_response.json()["detail"] == "Confirmed members count exceeds expedition capacity"


def test_chief_user_cannot_be_invited_as_member(client: TestClient):
    chief = register_user(client, "chief@example.com", "chief")
    invited_chief = register_user(client, "invited-chief@example.com", "chief")
    expedition = create_expedition(client, chief["access_token"])

    response = invite_member(client, chief["access_token"], expedition["id"], invited_chief["user"]["id"])

    assert response.status_code == 400
    assert response.json()["detail"] == "Only users with member role can be invited"


def test_confirming_existing_confirmation_is_rejected(client: TestClient):
    chief = register_user(client, "chief@example.com", "chief")
    expedition = create_expedition(client, chief["access_token"])
    member = create_confirmed_member(client, chief["access_token"], expedition["id"], "member@example.com")

    response = confirm_membership(client, member["access_token"], expedition["id"])

    assert response.status_code == 400
    assert response.json()["detail"] == "Only invited members can confirm participation"


def test_activation_rejects_member_already_in_another_active_expedition(client: TestClient):
    chief = register_user(client, "chief@example.com", "chief")
    first_member = register_user(client, "member-1@example.com")
    second_member = register_user(client, "member-2@example.com")

    first_expedition = create_expedition(client, chief["access_token"], capacity=2)
    for member in [first_member, second_member]:
        invite_response = invite_member(client, chief["access_token"], first_expedition["id"], member["user"]["id"])
        assert invite_response.status_code == 200, invite_response.text
    start_expedition_with_members(
        client,
        chief["access_token"],
        first_expedition["id"],
        [first_member["access_token"], second_member["access_token"]],
    )

    second_expedition = create_expedition(client, chief["access_token"], capacity=2)
    for member in [first_member, second_member]:
        invite_response = invite_member(client, chief["access_token"], second_expedition["id"], member["user"]["id"])
        assert invite_response.status_code == 200, invite_response.text
        confirm_response = confirm_membership(client, member["access_token"], second_expedition["id"])
        assert confirm_response.status_code == 200, confirm_response.text

    ready_response = update_status(client, chief["access_token"], second_expedition["id"], "ready")
    assert ready_response.status_code == 200, ready_response.text
    active_response = update_status(client, chief["access_token"], second_expedition["id"], "active")

    assert active_response.status_code == 400
    assert active_response.json()["detail"] == "Confirmed member already participates in another active expedition"


def test_invitation_rules(client: TestClient):
    chief = register_user(client, "chief@example.com", "chief")
    other_chief = register_user(client, "other-chief@example.com", "chief")
    invited_member = register_user(client, "invited@example.com")
    other_member = register_user(client, "other-member@example.com")
    expedition = create_expedition(client, chief["access_token"])

    chief_invite_response = invite_member(client, chief["access_token"], expedition["id"], other_chief["user"]["id"])
    assert chief_invite_response.status_code == 400
    assert chief_invite_response.json()["detail"] == "Only users with member role can be invited"

    invite_response = invite_member(client, chief["access_token"], expedition["id"], invited_member["user"]["id"])
    assert invite_response.status_code == 200, invite_response.text
    assert invite_response.json()["state"] == "invited"

    duplicate_invite_response = invite_member(
        client,
        chief["access_token"],
        expedition["id"],
        invited_member["user"]["id"],
    )
    assert duplicate_invite_response.status_code == 409

    other_member_confirm_response = confirm_membership(client, other_member["access_token"], expedition["id"])
    assert other_member_confirm_response.status_code == 404

    confirm_response = confirm_membership(client, invited_member["access_token"], expedition["id"])
    assert confirm_response.status_code == 200, confirm_response.text
    assert confirm_response.json()["state"] == "confirmed"

    confirm_again_response = confirm_membership(client, invited_member["access_token"], expedition["id"])
    assert confirm_again_response.status_code == 400


def test_invite_and_confirm_are_allowed_only_while_expedition_is_draft(client: TestClient):
    chief = register_user(client, "chief@example.com", "chief")
    expedition = create_expedition(client, chief["access_token"], capacity=2)
    first_member = create_confirmed_member(client, chief["access_token"], expedition["id"], "member-1@example.com")
    second_member = create_confirmed_member(client, chief["access_token"], expedition["id"], "member-2@example.com")
    third_member = register_user(client, "member-3@example.com")

    ready_response = update_status(client, chief["access_token"], expedition["id"], "ready")
    assert ready_response.status_code == 200, ready_response.text

    invite_response = invite_member(client, chief["access_token"], expedition["id"], third_member["user"]["id"])
    assert invite_response.status_code == 400

    confirm_response = confirm_membership(client, first_member["access_token"], expedition["id"])
    assert confirm_response.status_code == 400

    active_response = update_status(client, chief["access_token"], expedition["id"], "active")
    assert active_response.status_code == 200, active_response.text

    finish_response = update_status(client, chief["access_token"], expedition["id"], "finished")
    assert finish_response.status_code == 200, finish_response.text

    second_confirm_response = confirm_membership(client, second_member["access_token"], expedition["id"])
    assert second_confirm_response.status_code == 400


def test_websocket_rejects_invalid_token(client: TestClient):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/expeditions?token=invalid-token"):
            pass

    assert exc_info.value.code == 1008


def test_websocket_sends_events_to_authorized_expedition_users_only(client: TestClient):
    chief = register_user(client, "chief@example.com", "chief")
    member = register_user(client, "member@example.com")
    outsider = register_user(client, "outsider@example.com")
    expedition = create_expedition(client, chief["access_token"])
    outsider_messages: queue.Queue = queue.Queue()

    def receive_outsider_message():
        try:
            outsider_messages.put(outsider_ws.receive_json())
        except Exception:
            return

    with (
        client.websocket_connect(f"/ws/expeditions?token={chief['access_token']}") as chief_ws,
        client.websocket_connect(f"/ws/expeditions?token={member['access_token']}") as member_ws,
        client.websocket_connect(f"/ws/expeditions?token={outsider['access_token']}") as outsider_ws,
    ):
        outsider_thread = threading.Thread(
            target=receive_outsider_message,
            daemon=True,
        )
        outsider_thread.start()

        invite_response = invite_member(client, chief["access_token"], expedition["id"], member["user"]["id"])
        assert invite_response.status_code == 200, invite_response.text

        chief_invite_event = chief_ws.receive_json()
        member_invite_event = member_ws.receive_json()
        assert chief_invite_event == member_invite_event
        assert chief_invite_event["type"] == "member_invited"
        assert chief_invite_event["expedition_id"] == expedition["id"]
        assert chief_invite_event["user_id"] == member["user"]["id"]

        confirm_response = confirm_membership(client, member["access_token"], expedition["id"])
        assert confirm_response.status_code == 200, confirm_response.text

        chief_confirm_event = chief_ws.receive_json()
        member_confirm_event = member_ws.receive_json()
        assert chief_confirm_event == member_confirm_event
        assert chief_confirm_event["type"] == "member_confirmed"
        assert chief_confirm_event["expedition_id"] == expedition["id"]
        assert chief_confirm_event["user_id"] == member["user"]["id"]

        ready_response = update_status(client, chief["access_token"], expedition["id"], "ready")
        assert ready_response.status_code == 200, ready_response.text

        chief_status_event = chief_ws.receive_json()
        member_status_event = member_ws.receive_json()
        assert chief_status_event == member_status_event
        assert chief_status_event["type"] == "expedition_status"
        assert chief_status_event["expedition_id"] == expedition["id"]
        assert chief_status_event["old_status"] == "draft"
        assert chief_status_event["new_status"] == "ready"

        with pytest.raises(queue.Empty):
            outsider_messages.get(timeout=0.2)
