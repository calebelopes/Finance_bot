"""Phase 3 tests: chat input, transaction CRUD, KPI strip."""

import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from utils import db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db_file = str(tmp_path / "phase3.db")
    with patch.object(db, "_db_path", return_value=db_file):
        db.setup_database()
        from web import main as web_main  # noqa: PLC0415
        client = TestClient(web_main.app)
        # Auto-login a default user
        uid = db.create_web_user("alice", "secret123")
        token = db.create_session(uid)
        client.cookies.set("finance_session", token)
        yield client, uid


def _csrf(client) -> str:
    r = client.get("/app")
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    assert m is not None
    return m.group(1)


class TestAppView:
    def test_app_renders_for_logged_in(self, fresh_db):
        client, _ = fresh_db
        r = client.get("/app")
        assert r.status_code == 200
        assert "kpi-strip" in r.text
        assert "chat-form" in r.text

    def test_app_redirects_anonymous(self, fresh_db):
        client, _ = fresh_db
        client.cookies.clear()
        r = client.get("/app", follow_redirects=False)
        assert r.status_code == 303
        assert "/login" in r.headers["location"]

    def test_kpi_strip_initial_zero(self, fresh_db):
        client, _ = fresh_db
        r = client.get("/app")
        assert r.status_code == 200
        # No transactions yet → expense should render zero
        assert "0,00" in r.text or "0.00" in r.text


class TestChatStore:
    def test_chat_stores_expense(self, fresh_db):
        client, uid = fresh_db
        csrf = _csrf(client)

        r = client.post(
            "/app/chat",
            data={"text": "jantar 30,50", "csrf_token": csrf},
        )
        assert r.status_code == 200
        # Response is the new tx_row + KPI OOB
        assert "data-tx-row" in r.text
        assert "jantar" in r.text

        txs = db.get_transactions(uid, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert len(txs) == 1
        assert txs[0]["description"] == "jantar"
        assert txs[0]["amount_original"] == 30.5
        assert txs[0]["type"] == "expense"
        assert txs[0]["source"] == "web"

    def test_chat_stores_income(self, fresh_db):
        client, uid = fresh_db
        csrf = _csrf(client)

        r = client.post(
            "/app/chat",
            data={"text": "+salario 5000", "csrf_token": csrf},
        )
        assert r.status_code == 200
        txs = db.get_transactions(uid, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert len(txs) == 1
        assert txs[0]["type"] == "income"

    def test_chat_with_currency(self, fresh_db):
        client, uid = fresh_db
        csrf = _csrf(client)

        r = client.post(
            "/app/chat",
            data={"text": "dinner 30 usd", "csrf_token": csrf},
        )
        assert r.status_code == 200
        txs = db.get_transactions(uid, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert txs[0]["currency_code"] == "USD"

    def test_chat_invalid_returns_error_bubble(self, fresh_db):
        client, uid = fresh_db
        csrf = _csrf(client)

        r = client.post(
            "/app/chat",
            data={"text": "hello world without value", "csrf_token": csrf},
        )
        assert r.status_code == 200
        # Should not have stored anything
        txs = db.get_transactions(uid, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert len(txs) == 0

    def test_chat_greeting_returns_info_bubble(self, fresh_db):
        client, uid = fresh_db
        csrf = _csrf(client)

        r = client.post(
            "/app/chat",
            data={"text": "oi", "csrf_token": csrf},
        )
        assert r.status_code == 200
        txs = db.get_transactions(uid, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert len(txs) == 0

    def test_chat_empty_text_no_op(self, fresh_db):
        client, _ = fresh_db
        csrf = _csrf(client)
        r = client.post(
            "/app/chat",
            data={"text": "", "csrf_token": csrf},
        )
        assert r.status_code == 204

    def test_chat_csrf_required(self, fresh_db):
        client, _ = fresh_db
        r = client.post(
            "/app/chat",
            data={"text": "jantar 30", "csrf_token": "wrong"},
        )
        assert r.status_code == 400

    def test_chat_includes_kpi_oob_update(self, fresh_db):
        client, _ = fresh_db
        csrf = _csrf(client)

        r = client.post(
            "/app/chat",
            data={"text": "jantar 30", "csrf_token": csrf},
        )
        assert r.status_code == 200
        assert 'id="kpi-strip"' in r.text
        assert "hx-swap-oob" in r.text

    def test_chat_backdated_with_yesterday(self, fresh_db):
        client, uid = fresh_db
        csrf = _csrf(client)
        r = client.post(
            "/app/chat",
            data={"text": "ontem mercado 50", "csrf_token": csrf},
        )
        assert r.status_code == 200
        txs = db.get_transactions(uid, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert len(txs) == 1


class TestTransactionDelete:
    def test_delete_own_transaction(self, fresh_db):
        client, uid = fresh_db
        tx_id = db.store_transaction(uid, "alice", "jantar", 30.0, "Refeição", "expense")
        r = client.delete(f"/api/transactions/{tx_id}")
        assert r.status_code == 200
        # Response is the OOB KPI partial
        assert 'id="kpi-strip"' in r.text
        # Underlying data is gone
        txs = db.get_transactions(uid, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert len(txs) == 0

    def test_delete_someone_elses_404(self, fresh_db):
        client, _ = fresh_db
        # Create another user with a transaction
        other = db.create_web_user("bob", "pass1234")
        tx_id = db.store_transaction(other, "bob", "jantar", 30.0, "Refeição")
        r = client.delete(f"/api/transactions/{tx_id}")
        assert r.status_code == 404
        # Underlying row still exists
        txs = db.get_transactions(other, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert len(txs) == 1

    def test_delete_not_found(self, fresh_db):
        client, _ = fresh_db
        r = client.delete("/api/transactions/99999")
        assert r.status_code == 404

    def test_delete_requires_login(self, fresh_db):
        client, uid = fresh_db
        tx_id = db.store_transaction(uid, "alice", "jantar", 30.0, "Refeição")
        client.cookies.clear()
        r = client.delete(f"/api/transactions/{tx_id}", follow_redirects=False)
        assert r.status_code == 303


class TestCategoryFix:
    def test_fix_own_category(self, fresh_db):
        client, uid = fresh_db
        tx_id = db.store_transaction(uid, "alice", "jantar", 30.0, "Outros")
        csrf = _csrf(client)

        r = client.post(
            f"/api/transactions/{tx_id}/category",
            data={"category": "Refeição", "csrf_token": csrf},
        )
        assert r.status_code == 200
        with db._connect() as conn:
            row = conn.execute(
                "SELECT category FROM transactions WHERE id = ?", (tx_id,)
            ).fetchone()
        assert row["category"] == "Refeição"

    def test_fix_others_category_404(self, fresh_db):
        client, _ = fresh_db
        other = db.create_web_user("carol", "pass1234")
        tx_id = db.store_transaction(other, "carol", "jantar", 30.0, "Outros")
        csrf = _csrf(client)

        r = client.post(
            f"/api/transactions/{tx_id}/category",
            data={"category": "Refeição", "csrf_token": csrf},
        )
        assert r.status_code == 404

    def test_fix_csrf_required(self, fresh_db):
        client, uid = fresh_db
        tx_id = db.store_transaction(uid, "alice", "jantar", 30.0, "Outros")
        r = client.post(
            f"/api/transactions/{tx_id}/category",
            data={"category": "Refeição", "csrf_token": "bogus"},
        )
        assert r.status_code == 400


class TestUserIsolation:
    def test_kpi_only_counts_own_transactions(self, fresh_db):
        client, uid = fresh_db
        # Logged-in user has 100 expense
        db.store_transaction(uid, "alice", "jantar", 100.0, "Refeição")
        # Another user has 999 — should not affect alice's KPI
        other = db.create_web_user("bob", "pass1234")
        db.store_transaction(other, "bob", "carro", 999.0, "Outros")

        r = client.get("/app")
        assert r.status_code == 200
        # alice's expense is 100
        assert "100,00" in r.text or "100.00" in r.text
        # bob's expense should NOT appear
        assert "999,00" not in r.text and "999.00" not in r.text

    def test_recent_transactions_isolated(self, fresh_db):
        client, uid = fresh_db
        db.store_transaction(uid, "alice", "alicemeal", 10.0, "Refeição")
        other = db.create_web_user("bob", "pass1234")
        db.store_transaction(other, "bob", "bobmeal", 20.0, "Refeição")

        r = client.get("/app")
        assert "alicemeal" in r.text
        assert "bobmeal" not in r.text
