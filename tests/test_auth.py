"""Week 7: password hashing, lockout, sessions, and role-based access (POPIA least privilege)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.auth import service
from app.auth.passwords import hash_password, verify_password
from tests.conftest import TEST_PASSWORD, add_staff, login_headers

NOW = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)


# ---- Passwords ------------------------------------------------------------
def test_password_hash_is_salted_and_verifiable():
    a, b = hash_password("correct horse battery"), hash_password("correct horse battery")
    assert a != b                                   # a new random salt every time
    assert a.startswith("pbkdf2_sha256$1000$")      # iterations from the setting, stored in the hash
    assert "correct horse" not in a
    assert verify_password("correct horse battery", a)
    assert not verify_password("correct horse batterY", a)


def test_verify_rejects_malformed_hashes():
    assert not verify_password("x", "")
    assert not verify_password("x", "md5$1$00$00")
    assert not verify_password("x", "pbkdf2_sha256$notanumber$00$00")


def test_create_staff_validation(db_session):
    with pytest.raises(ValueError, match="Unknown role"):
        add_staff(db_session, "Mr X", "janitor")
    with pytest.raises(ValueError, match="at least"):
        service.create_staff(db_session, "Mr X", "x@test.example", "admin_clerk", "short")
    add_staff(db_session, "Mr X", "admin_clerk", email="X@Test.example")
    with pytest.raises(ValueError, match="already exists"):
        add_staff(db_session, "Mr Y", "admin_clerk", email="x@test.example")   # emails are case-insensitive


# ---- Lockout --------------------------------------------------------------
def test_five_failed_logins_lock_the_account_for_15_minutes(db_session):
    staff = add_staff(db_session, "Mrs Pillay", "finance_clerk")
    for _ in range(4):
        with pytest.raises(service.LoginError) as err:
            service.authenticate(db_session, staff.email, "wrong", now=NOW)
        assert not err.value.locked
    with pytest.raises(service.LoginError) as err:
        service.authenticate(db_session, staff.email, "wrong", now=NOW)
    assert err.value.locked
    # Even the right password is refused while locked...
    with pytest.raises(service.LoginError):
        service.authenticate(db_session, staff.email, TEST_PASSWORD, now=NOW + timedelta(minutes=14))
    # ...and works again after 15 minutes.
    assert service.authenticate(db_session, staff.email, TEST_PASSWORD, now=NOW + timedelta(minutes=15)).id == staff.id


def test_successful_login_resets_the_failure_count(db_session):
    staff = add_staff(db_session, "Mrs Pillay", "finance_clerk")
    for _ in range(4):
        with pytest.raises(service.LoginError):
            service.authenticate(db_session, staff.email, "wrong", now=NOW)
    service.authenticate(db_session, staff.email, TEST_PASSWORD, now=NOW)
    assert staff.failed_logins == 0
    with pytest.raises(service.LoginError) as err:     # one more failure does not lock
        service.authenticate(db_session, staff.email, "wrong", now=NOW)
    assert not err.value.locked


def test_unknown_and_inactive_accounts_get_the_same_message(db_session):
    add_staff(db_session, "Mr Gone", "it_support", active=False)
    messages = set()
    for email in ("nobody@test.example", "it_support.gone@test.example"):
        with pytest.raises(service.LoginError) as err:
            service.authenticate(db_session, email, TEST_PASSWORD, now=NOW)
        messages.add(str(err.value))
    assert messages == {"Invalid email or password"}


# ---- Sessions -------------------------------------------------------------
def test_token_expires_after_8_hours_and_only_its_hash_is_stored(db_session):
    from app.models import StaffSession

    staff = add_staff(db_session, "Mr Nel", "class_teacher")
    token, expires = service.start_session(db_session, staff, now=NOW)
    assert expires == NOW + timedelta(hours=8)
    stored = db_session.query(StaffSession).one()
    assert stored.token_hash == service.token_hash(token) and token not in stored.token_hash
    assert service.staff_for_token(db_session, token, now=NOW + timedelta(hours=7, minutes=59)).id == staff.id
    assert service.staff_for_token(db_session, token, now=NOW + timedelta(hours=8)) is None
    assert service.staff_for_token(db_session, "made-up-token", now=NOW) is None


def test_deactivated_staff_lose_access_immediately(db_session):
    staff = add_staff(db_session, "Mr Nel", "class_teacher")
    token, _ = service.start_session(db_session, staff, now=NOW)
    staff.active = False
    db_session.commit()
    assert service.staff_for_token(db_session, token, now=NOW) is None


# ---- Endpoints ------------------------------------------------------------
def test_login_me_logout(anon_client, db_session):
    staff = add_staff(db_session, "Mrs Pillay", "finance_clerk")
    r = anon_client.post("/auth/login", json={"email": staff.email.upper(), "password": TEST_PASSWORD})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"
    assert "password_hash" not in r.json()["staff"]
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    assert anon_client.get("/auth/me", headers=headers).json()["role"] == "finance_clerk"
    assert anon_client.post("/auth/logout", headers=headers).status_code == 204
    assert anon_client.get("/auth/me", headers=headers).status_code == 401


def test_login_errors(anon_client, db_session):
    staff = add_staff(db_session, "Mrs Pillay", "finance_clerk")
    assert anon_client.post("/auth/login", json={"email": staff.email, "password": "nope"}).status_code == 401
    for _ in range(4):
        anon_client.post("/auth/login", json={"email": staff.email, "password": "nope"})
    locked = anon_client.post("/auth/login", json={"email": staff.email, "password": TEST_PASSWORD})
    assert locked.status_code == 423 and "15 minutes" in locked.json()["detail"]


@pytest.mark.parametrize("method,path", [
    ("GET", "/tickets"), ("GET", "/tickets/1"), ("PATCH", "/tickets/1/status"),
    ("GET", "/tickets/1/audit"), ("GET", "/tickets/1/responses"), ("POST", "/responses/1/approve"),
    ("GET", "/forecast"), ("GET", "/risk/summary"), ("GET", "/risk/report.pdf"), ("GET", "/auth/me"),
])
def test_staff_endpoints_need_a_login(anon_client, method, path):
    response = anon_client.request(method, path, json={})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_parent_endpoints_still_work_without_login(anon_client):
    created = anon_client.post("/tickets", json={"message": "When is the next parents evening?"})
    assert created.status_code == 201
    assert anon_client.get(f"/tickets/by-reference/{created.json()['reference']}").status_code == 200
    assert anon_client.get("/stats").status_code == 200 and anon_client.get("/health").status_code == 200


def test_expired_token_is_refused_by_the_api(anon_client, db_session):
    staff = add_staff(db_session, "Mr Nel", "class_teacher")
    token, _ = service.start_session(db_session, staff, now=datetime.now(timezone.utc) - timedelta(hours=9))
    assert anon_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


# ---- Least privilege ------------------------------------------------------
def _ticket(client, message):
    r = client.post("/tickets", json={"message": message})
    assert r.status_code == 201
    return r.json()


def test_welfare_tickets_only_visible_to_deputy_and_principal(client, login_as):
    welfare = _ticket(client, "My son is being bullied every day at break")
    fees = _ticket(client, "Please send me the fee statement")
    _, clerk = login_as("finance_clerk", "Mrs Pillay")
    _, teacher = login_as("class_teacher", "Mr Nel")
    _, deputy = login_as("deputy_principal", "Mr Mokoena")

    assert [t["id"] for t in client.get("/tickets", headers=clerk).json()] == [fees["id"]]
    assert client.get(f"/tickets/{welfare['id']}", headers=clerk).status_code == 404      # not revealed
    assert client.get(f"/tickets/{welfare['id']}/audit", headers=teacher).status_code == 404
    assert client.get(f"/tickets/{welfare['id']}", headers=deputy).status_code == 200
    assert {t["id"] for t in client.get("/tickets").json()} == {welfare["id"], fees["id"]}   # principal


def test_deputy_sees_safety_flagged_tickets_in_other_categories(client, login_as, db_session):
    from app.models import Ticket

    t = _ticket(client, "The transport driver shouted and hit my child")
    ticket = db_session.get(Ticket, t["id"])
    ticket.category, ticket.routed_role, ticket.safety_flag = "transport", "admin_clerk", True
    db_session.commit()
    _, clerk = login_as("admin_clerk")
    _, deputy = login_as("deputy_principal")
    assert client.get(f"/tickets/{t['id']}", headers=clerk).status_code == 404
    assert client.get(f"/tickets/{t['id']}", headers=deputy).status_code == 200


def test_staff_only_see_tickets_routed_to_their_role(client, login_as):
    portal = _ticket(client, "I forgot my portal password")
    _ticket(client, "Is there space in Grade 1 next year?")
    _, it = login_as("it_support")
    assert [t["id"] for t in client.get("/tickets", headers=it).json()] == [portal["id"]]


def test_forecast_and_risk_are_for_senior_staff_only(client, login_as):
    _, clerk = login_as("finance_clerk")
    _, deputy = login_as("deputy_principal")
    for path in ("/risk/summary", "/risk/fairness", "/forecast", "/forecast/workload", "/analytics/history"):
        r = client.get(path, headers=clerk)
        assert r.status_code == 403 and "Principal" in r.json()["detail"]
    assert client.get("/risk/summary", headers=deputy).status_code == 200


def test_actor_is_the_logged_in_staff_member_not_a_typed_name(client, login_as):
    t = _ticket(client, "When is the exam timetable out?")
    _, teacher = login_as("class_teacher", "Mr Nel")
    client.patch(f"/tickets/{t['id']}/classification", headers=teacher,
                 json={"urgency": "high", "actor": "Someone Else", "reason": "exam tomorrow"})
    override = client.get(f"/tickets/{t['id']}/audit").json()[-1]
    assert override["actor"] == "Mr Nel"


def test_login_headers_helper(anon_client, db_session):
    staff = add_staff(db_session, "Mr Nel", "class_teacher")
    assert login_headers(anon_client, staff.email)["Authorization"].startswith("Bearer ")
