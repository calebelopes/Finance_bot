from unittest.mock import patch

import pytest

from utils import db


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    db_file = str(tmp_path / "test.db")
    with patch.object(db, "_db_path", return_value=db_file):
        db.setup_database()
        yield db_file


class TestSetupDatabase:
    def test_tables_created(self):
        with db._connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            tables = {r["name"] for r in rows}
        assert {"users", "actions", "app_events", "usage_events"} <= tables


class TestStoreAction:
    def test_store_and_retrieve(self):
        action_id = db.store_action(123, "testuser", "jantar", 20.5, "Refeição")
        assert action_id is not None

        actions = db.get_actions(123, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert len(actions) == 1
        assert actions[0]["action"] == "jantar"
        assert actions[0]["value"] == 20.5
        assert actions[0]["category"] == "Refeição"

    def test_returns_incrementing_ids(self):
        id1 = db.store_action(123, "u", "a", 1.0, "Outros")
        id2 = db.store_action(123, "u", "b", 2.0, "Outros")
        assert id2 > id1

    def test_multiple_actions(self):
        db.store_action(123, "testuser", "jantar", 20.0, "Refeição")
        db.store_action(123, "testuser", "uber", 15.0, "Transporte")

        actions = db.get_actions(123, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert len(actions) == 2

    def test_user_isolation(self):
        db.store_action(100, "user_a", "jantar", 20.0, "Refeição")
        db.store_action(200, "user_b", "almoço", 15.0, "Refeição")

        assert len(db.get_actions(100, "2000-01-01T00:00:00", "2099-12-31T23:59:59")) == 1
        assert len(db.get_actions(200, "2000-01-01T00:00:00", "2099-12-31T23:59:59")) == 1

    def test_also_logs_usage_event(self):
        db.store_action(123, "testuser", "jantar", 20.0, "Refeição")
        with db._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM usage_events WHERE user_id = 123"
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["event_type"] == "action_stored"


class TestDeleteAction:
    def test_delete_own_action(self):
        action_id = db.store_action(123, "testuser", "jantar", 20.0, "Refeição")
        assert db.delete_action(123, action_id) is True

        actions = db.get_actions(123, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert len(actions) == 0

    def test_cannot_delete_others_action(self):
        action_id = db.store_action(123, "testuser", "jantar", 20.0, "Refeição")
        assert db.delete_action(999, action_id) is False

        actions = db.get_actions(123, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert len(actions) == 1

    def test_delete_nonexistent(self):
        assert db.delete_action(123, 99999) is False


class TestEditAction:
    def test_edit_own_action(self):
        action_id = db.store_action(123, "testuser", "jantar", 20.0, "Refeição")
        assert db.edit_action_value(123, action_id, 30.0) is True

        actions = db.get_actions(123, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert actions[0]["value"] == 30.0

    def test_cannot_edit_others_action(self):
        action_id = db.store_action(123, "testuser", "jantar", 20.0, "Refeição")
        assert db.edit_action_value(999, action_id, 30.0) is False

        actions = db.get_actions(123, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert actions[0]["value"] == 20.0

    def test_edit_nonexistent(self):
        assert db.edit_action_value(123, 99999, 30.0) is False


class TestStoreIncome:
    def test_store_income(self):
        action_id = db.store_action(123, "testuser", "salary", 5000.0, "Salário", "income")
        assert action_id is not None
        actions = db.get_actions(123, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert len(actions) == 1
        assert actions[0]["type"] == "income"
        assert actions[0]["category"] == "Salário"

    def test_default_type_is_expense(self):
        db.store_action(123, "testuser", "jantar", 20.0, "Refeição")
        actions = db.get_actions(123, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert actions[0]["type"] == "expense"


class TestSummaryByCategory:
    def test_groups_by_category(self):
        db.store_action(123, "u", "jantar", 20.0, "Refeição")
        db.store_action(123, "u", "almoço", 15.0, "Refeição")
        db.store_action(123, "u", "uber", 25.0, "Transporte")

        summary = db.get_summary_by_category(123, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        by_cat = {r["category"]: r for r in summary}

        assert by_cat["Refeição"]["total"] == 35.0
        assert by_cat["Refeição"]["count"] == 2
        assert by_cat["Transporte"]["total"] == 25.0
        assert by_cat["Transporte"]["count"] == 1

    def test_filter_by_type(self):
        db.store_action(123, "u", "jantar", 20.0, "Refeição", "expense")
        db.store_action(123, "u", "salary", 5000.0, "Salário", "income")

        expenses = db.get_summary_by_category(123, "2000-01-01T00:00:00", "2099-12-31T23:59:59", "expense")
        income = db.get_summary_by_category(123, "2000-01-01T00:00:00", "2099-12-31T23:59:59", "income")

        assert len(expenses) == 1
        assert expenses[0]["category"] == "Refeição"
        assert len(income) == 1
        assert income[0]["category"] == "Salário"

    def test_empty_when_no_data(self):
        summary = db.get_summary_by_category(123, "2000-01-01T00:00:00", "2099-12-31T23:59:59")
        assert summary == []


class TestLogAppEvent:
    def test_logs_event(self):
        db.log_app_event("app_started")
        with db._connect() as conn:
            rows = conn.execute("SELECT * FROM app_events").fetchall()
        assert len(rows) == 1
        assert rows[0]["event_type"] == "app_started"


class TestLanguage:
    def test_default_lang_is_pt(self):
        db.store_action(123, "testuser", "jantar", 20.0, "Refeição")
        assert db.get_user_lang(123) == "pt"

    def test_set_and_get_lang(self):
        db.store_action(123, "testuser", "jantar", 20.0, "Refeição")
        db.set_lang(123, "en")
        assert db.get_user_lang(123) == "en"

    def test_ensure_user_with_lang(self):
        db.ensure_user_with_lang(500, "languser", "ja")
        assert db.get_user_lang(500) == "ja"

    def test_authenticate_returns_lang(self):
        db.store_action(300, "authuser", "jantar", 10.0, "Refeição")
        db.set_password(300, "mypass")
        db.set_lang(300, "en")
        result = db.authenticate_user("authuser", "mypass")
        assert result is not None
        assert result["lang"] == "en"
