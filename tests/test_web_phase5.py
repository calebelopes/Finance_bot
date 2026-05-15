"""Phase 5 tests: recurring CRUD, admin panel, telegram link flow end-to-end."""

import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from utils import db


@pytest.fixture
def client_factory(tmp_path):
    db_file = str(tmp_path / "phase5.db")
    with patch.object(db, "_db_path", return_value=db_file):
        db.setup_database()
        from web import main as web_main  # noqa: PLC0415

        def _make(username="alice", password="pass1234", admin=False):
            uid = db.create_web_user(
                username, password, email=f"{username}@example.com"
            )
            if admin:
                db.set_admin(uid, True)
            client = TestClient(web_main.app)
            token = db.create_session(uid)
            client.cookies.set("finance_session", token)
            return client, uid

        yield _make


def _csrf(client, path="/recurring") -> str:
    r = client.get(path)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    assert m is not None
    return m.group(1)


class TestRecurringCRUD:
    def test_recurring_page_renders(self, client_factory):
        client, _ = client_factory()
        r = client.get("/recurring")
        assert r.status_code == 200

    def test_add_recurring_expense(self, client_factory):
        client, uid = client_factory()
        csrf = _csrf(client)
        r = client.post(
            "/recurring",
            data={
                "description": "aluguel", "amount": "1500", "type": "expense",
                "day": "5", "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        rules = db.get_recurring(uid)
        assert len(rules) == 1
        assert rules[0]["description"] == "aluguel"
        assert rules[0]["amount"] == 1500.0
        assert rules[0]["type"] == "expense"
        assert rules[0]["day_of_month"] == 5

    def test_add_recurring_income(self, client_factory):
        client, uid = client_factory()
        csrf = _csrf(client)
        r = client.post(
            "/recurring",
            data={"description": "salario", "amount": "5000", "type": "income",
                  "day": "1", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert r.status_code == 303
        rules = db.get_recurring(uid)
        assert rules[0]["type"] == "income"

    def test_toggle_recurring(self, client_factory):
        client, uid = client_factory()
        rec_id = db.add_recurring(uid, "netflix", 30.0, "Lazer")
        csrf = _csrf(client)
        r = client.post(
            f"/recurring/{rec_id}/toggle",
            data={"csrf_token": csrf}, follow_redirects=False,
        )
        assert r.status_code == 303
        rules = db.get_recurring(uid)
        assert rules[0]["active"] == 0

    def test_delete_recurring(self, client_factory):
        client, uid = client_factory()
        rec_id = db.add_recurring(uid, "spotify", 20.0, "Lazer")
        csrf = _csrf(client)
        r = client.post(
            f"/recurring/{rec_id}/delete",
            data={"csrf_token": csrf}, follow_redirects=False,
        )
        assert r.status_code == 303
        assert db.get_recurring(uid) == []

    def test_recurring_isolated_per_user(self, client_factory):
        client, _uid = client_factory("alice")
        other_uid = db.create_web_user("bob", "pass1234")
        rec_id = db.add_recurring(other_uid, "bob_rule", 100.0, "Outros")
        csrf = _csrf(client)
        # alice cannot delete bob's rule
        r = client.post(
            f"/recurring/{rec_id}/delete",
            data={"csrf_token": csrf}, follow_redirects=False,
        )
        assert r.status_code == 404

    def test_invalid_amount_rejected(self, client_factory):
        client, _ = client_factory()
        csrf = _csrf(client)
        r = client.post(
            "/recurring",
            data={"description": "test", "amount": "abc", "type": "expense",
                  "csrf_token": csrf},
        )
        assert r.status_code == 400

    def test_csrf_required(self, client_factory):
        client, _ = client_factory()
        r = client.post(
            "/recurring",
            data={"description": "test", "amount": "10",
                  "type": "expense", "csrf_token": "wrong"},
        )
        assert r.status_code == 400


class TestAdminPanel:
    def test_non_admin_gets_404(self, client_factory):
        client, _ = client_factory()
        r = client.get("/admin")
        assert r.status_code == 404

    def test_admin_renders(self, client_factory):
        client, _ = client_factory(admin=True)
        r = client.get("/admin")
        assert r.status_code == 200
        # Default no-data state when no transactions exist
        # but the user table renders at least the admin user
        assert "alice" in r.text

    def test_admin_shows_users_with_data(self, client_factory):
        client, uid = client_factory(admin=True)
        # Seed transactions
        db.store_transaction(uid, "alice", "jantar", 30.0, "Refeição")
        db.store_transaction(uid, "alice", "salario", 5000.0, "Salário", "income")

        r = client.get("/admin")
        assert r.status_code == 200
        assert "alice" in r.text

    def test_admin_total_tx_kpi(self, client_factory):
        client, uid = client_factory(admin=True)
        db.store_transaction(uid, "alice", "a", 10.0, "Outros")
        db.store_transaction(uid, "alice", "b", 20.0, "Outros")
        r = client.get("/admin")
        assert r.status_code == 200
        # KPI block contains "2" for total transactions
        # (rough check — exact 2 may not be unique, so look for "2" alongside admin_kpi_total_tx label)
        assert ">2<" in r.text


class TestTelegramLinkFlow:
    def test_generate_code_then_simulate_bot_consume(self, client_factory):
        # 1. User generates a link code via the web
        client, uid = client_factory()
        r = client.get("/settings")
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
        r = client.post("/settings/link-telegram", data={"csrf_token": csrf})
        assert r.status_code == 200
        m = re.search(r'class="font-mono text-5xl[^"]*">\s*(\d{6})\s*<', r.text)
        assert m is not None
        code = m.group(1)

        # 2. Simulate bot side: consume code, link telegram_id to user
        consumed = db.consume_telegram_link_code(code)
        assert consumed == uid
        ok = db.link_telegram_to_user(uid, 12345)
        assert ok is True

        # 3. Future bot updates resolve to the same local user
        from utils.auth import resolve_telegram_user
        resolved_id, _ = resolve_telegram_user(12345, "alice", "pt")
        assert resolved_id == uid

    def test_expired_code_rejected(self, client_factory, tmp_path):
        _, uid = client_factory()
        code = db.create_telegram_link_code(uid, ttl_minutes=10)
        # Manually expire the code
        with db._connect() as conn:
            conn.execute(
                "UPDATE telegram_link_codes SET expires_at = '2000-01-01T00:00:00+00:00' WHERE code = ?",
                (code,),
            )
            conn.commit()
        assert db.consume_telegram_link_code(code) is None

    def test_link_collision_blocks_second_user(self, client_factory):
        # Two web users; one already has Telegram linked
        client_a, uid_a = client_factory("alpha")
        uid_b = db.create_web_user("beta", "pass1234")
        assert db.link_telegram_to_user(uid_a, 22222) is True
        # Bot user 22222 tries to link to a different web account → must fail
        assert db.link_telegram_to_user(uid_b, 22222) is False
