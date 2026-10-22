"""API endpoints, using an in-memory database."""

import re

from app.taxonomy import CATEGORIES


def create(client, message="I paid the school fees but my statement is wrong", **extra):
    response = client.post("/tickets", json={"message": message, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_taxonomy(client):
    data = client.get("/taxonomy").json()
    assert {c["code"] for c in data["categories"]} == set(CATEGORIES)


def test_classify_does_not_save(client):
    response = client.post("/classify", json={"message": "Forgot my portal password"})
    assert response.json()["category"] == "it_portal"
    assert client.get("/stats").json()["total"] == 0


def test_classify_rejects_empty(client):
    assert client.post("/classify", json={"message": ""}).status_code == 422


def test_create_ticket_returns_reference(client):
    data = create(client)
    assert re.fullmatch(r"SC-\d{8}-\d{4}", data["reference"])
    assert data["category"] == "fees_exemptions"
    assert data["routed_role"] == "finance_clerk"
    assert data["safety_notice"] is None
    # The parent's response never echoes personal details.
    assert "parent_name" not in data


def test_references_increment(client):
    first = create(client)["reference"]
    second = create(client)["reference"]
    assert first.endswith("-0001") and second.endswith("-0002")


def test_critical_ticket_shows_emergency_numbers(client):
    data = create(client, "My son didnt come home from school and his phone is off")
    assert data["urgency"] == "critical"
    assert "10111" in data["safety_notice"] and "112" in data["safety_notice"]


def test_blank_message_rejected(client):
    assert client.post("/tickets", json={"message": "   "}).status_code == 422


def test_invalid_grade_rejected(client):
    assert client.post("/tickets", json={"message": "hi", "learner_grade": "15"}).status_code == 422


def test_list_and_filter(client):
    create(client)
    create(client, "Forgot my portal password")
    assert len(client.get("/tickets").json()) == 2
    only_it = client.get("/tickets", params={"category": "it_portal"}).json()
    assert len(only_it) == 1 and only_it[0]["category"] == "it_portal"
    assert len(client.get("/tickets", params={"search": "password"}).json()) == 1


def test_invalid_filter_value_rejected(client):
    assert client.get("/tickets", params={"category": "pizza"}).status_code == 422


def test_get_ticket_and_404(client):
    ticket_id = create(client)["id"]
    assert client.get(f"/tickets/{ticket_id}").json()["id"] == ticket_id
    assert client.get("/tickets/9999").status_code == 404


def test_by_reference_is_public_and_hides_personal_data(client):
    ref = create(client, parent_name="Test Parent", parent_contact="test@example.com")["reference"]
    data = client.get(f"/tickets/by-reference/{ref.lower()}").json()  # case-insensitive
    assert data["reference"] == ref
    assert "message" not in data and "parent_name" not in data and "parent_contact" not in data
    assert client.get("/tickets/by-reference/SC-00000000-0000").status_code == 404


def test_status_update_sets_and_clears_resolved_at(client):
    ticket_id = create(client)["id"]
    resolved = client.patch(f"/tickets/{ticket_id}/status", json={"status": "resolved"}).json()
    assert resolved["status"] == "resolved" and resolved["resolved_at"]
    reopened = client.patch(f"/tickets/{ticket_id}/status", json={"status": "in_progress"}).json()
    assert reopened["resolved_at"] is None
    assert client.patch(f"/tickets/{ticket_id}/status", json={"status": "done"}).status_code == 422


def test_stats(client):
    create(client)
    create(client, "My son didnt come home")
    stats = client.get("/stats").json()
    assert stats["total"] == 2
    assert stats["by_category"]["fees_exemptions"] == 1
    assert stats["open_critical"] == 1
    assert set(stats["by_urgency"]) == {"low", "medium", "high", "critical"}


def test_api_key_protects_writes_and_personal_data(client, set_env):
    set_env(API_KEY="secret")
    assert client.post("/tickets", json={"message": "hi"}).status_code == 401
    assert client.get("/tickets").status_code == 401
    assert client.post("/tickets", json={"message": "hi"}, headers={"X-API-Key": "wrong"}).status_code == 401
    ok = client.post("/tickets", json={"message": "hi"}, headers={"X-API-Key": "secret"})
    assert ok.status_code == 201
    # Public endpoints stay open.
    assert client.get("/health").status_code == 200
    assert client.get("/stats").status_code == 200
    assert client.post("/classify", json={"message": "hi"}).status_code == 200
