from unittest.mock import patch

import pytest

from utils import db


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    db_file = str(tmp_path / "test.db")
    with patch.object(db, "_db_path", return_value=db_file):
        db.setup_database()
        yield db_file


_WIDE_RANGE = ("2000-01-01T00:00:00", "2099-12-31T23:59:59")


class TestSetupDatabase:
    def test_core_tables_created(self):
        with db._connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            tables = {r["name"] for r in rows}
        assert {"users", "transactions", "app_events", "usage_events"} <= tables

    def test_new_reference_tables_created(self):
        with db._connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            tables = {r["name"] for r in rows}
        expected = {
            "currencies", "categories", "category_aliases",
            "user_preferences", "exchange_rates",
            "recurring_transactions", "recurring_logs",
        }
        assert expected <= tables

    def test_currencies_seeded(self):
        with db._connect() as conn:
            rows = conn.execute("SELECT code FROM currencies").fetchall()
        codes = {r["code"] for r in rows}
        assert {"BRL", "USD", "EUR", "JPY", "GBP"} <= codes

    def test_categories_seeded(self):
        with db._connect() as conn:
            rows = conn.execute("SELECT name_key, type FROM categories").fetchall()
        cats = {r["name_key"]: r["type"] for r in rows}
        assert cats["Alimentação"] == "expense"
        assert cats["Salário"] == "income"
        assert cats["Outros"] == "expense"
        assert cats["Renda Extra"] == "income"

    def test_category_aliases_seeded(self):
        with db._connect() as conn:
            rows = conn.execute(
                "SELECT alias, lang FROM category_aliases WHERE alias = 'grocery'"
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["lang"] == "en"


class TestStoreTransaction:
    def test_store_and_retrieve(self):
        tx_id = db.store_transaction(123, "testuser", "jantar", 20.5, "Refeição")
        assert tx_id is not None

        txs = db.get_transactions(123, *_WIDE_RANGE)
        assert len(txs) == 1
        assert txs[0]["description"] == "jantar"
        assert txs[0]["amount_original"] == 20.5
        assert txs[0]["category"] == "Refeição"

    def test_returns_incrementing_ids(self):
        id1 = db.store_transaction(123, "u", "a", 1.0, "Outros")
        id2 = db.store_transaction(123, "u", "b", 2.0, "Outros")
        assert id2 > id1

    def test_multiple_transactions(self):
        db.store_transaction(123, "testuser", "jantar", 20.0, "Refeição")
        db.store_transaction(123, "testuser", "uber", 15.0, "Transporte")

        txs = db.get_transactions(123, *_WIDE_RANGE)
        assert len(txs) == 2

    def test_user_isolation(self):
        db.store_transaction(100, "user_a", "jantar", 20.0, "Refeição")
        db.store_transaction(200, "user_b", "almoço", 15.0, "Refeição")

        assert len(db.get_transactions(100, *_WIDE_RANGE)) == 1
        assert len(db.get_transactions(200, *_WIDE_RANGE)) == 1

    def test_also_logs_usage_event(self):
        db.store_transaction(123, "testuser", "jantar", 20.0, "Refeição")
        with db._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM usage_events WHERE user_id = 123"
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["event_type"] == "action_stored"

    def test_auto_resolves_category_id(self):
        db.store_transaction(123, "testuser", "jantar", 20.0, "Refeição")
        txs = db.get_transactions(123, *_WIDE_RANGE)
        assert txs[0]["category_id"] is not None
        cat_id = db.get_category_id("Refeição")
        assert txs[0]["category_id"] == cat_id

    def test_stores_source_field(self):
        db.store_transaction(123, "testuser", "jantar", 20.0, "Refeição", source="dashboard")
        txs = db.get_transactions(123, *_WIDE_RANGE)
        assert txs[0]["source"] == "dashboard"

    def test_default_source_is_text(self):
        db.store_transaction(123, "testuser", "jantar", 20.0, "Refeição")
        txs = db.get_transactions(123, *_WIDE_RANGE)
        assert txs[0]["source"] == "text"


class TestDeleteTransaction:
    def test_delete_own(self):
        tx_id = db.store_transaction(123, "testuser", "jantar", 20.0, "Refeição")
        assert db.delete_transaction(123, tx_id) is True

        txs = db.get_transactions(123, *_WIDE_RANGE)
        assert len(txs) == 0

    def test_cannot_delete_others(self):
        tx_id = db.store_transaction(123, "testuser", "jantar", 20.0, "Refeição")
        assert db.delete_transaction(999, tx_id) is False

        txs = db.get_transactions(123, *_WIDE_RANGE)
        assert len(txs) == 1

    def test_delete_nonexistent(self):
        assert db.delete_transaction(123, 99999) is False


class TestEditTransaction:
    def test_edit_own(self):
        tx_id = db.store_transaction(123, "testuser", "jantar", 20.0, "Refeição")
        assert db.edit_transaction(123, tx_id, 30.0) is True

        txs = db.get_transactions(123, *_WIDE_RANGE)
        assert txs[0]["amount_original"] == 30.0

    def test_cannot_edit_others(self):
        tx_id = db.store_transaction(123, "testuser", "jantar", 20.0, "Refeição")
        assert db.edit_transaction(999, tx_id, 30.0) is False

        txs = db.get_transactions(123, *_WIDE_RANGE)
        assert txs[0]["amount_original"] == 20.0

    def test_edit_nonexistent(self):
        assert db.edit_transaction(123, 99999, 30.0) is False


class TestStoreIncome:
    def test_store_income(self):
        tx_id = db.store_transaction(123, "testuser", "salary", 5000.0, "Salário", "income")
        assert tx_id is not None
        txs = db.get_transactions(123, *_WIDE_RANGE)
        assert len(txs) == 1
        assert txs[0]["type"] == "income"
        assert txs[0]["category"] == "Salário"

    def test_default_type_is_expense(self):
        db.store_transaction(123, "testuser", "jantar", 20.0, "Refeição")
        txs = db.get_transactions(123, *_WIDE_RANGE)
        assert txs[0]["type"] == "expense"


class TestSummaryByCategory:
    def test_groups_by_category(self):
        db.store_transaction(123, "u", "jantar", 20.0, "Refeição")
        db.store_transaction(123, "u", "almoço", 15.0, "Refeição")
        db.store_transaction(123, "u", "uber", 25.0, "Transporte")

        summary = db.get_summary_by_category(123, *_WIDE_RANGE)
        by_cat = {r["category"]: r for r in summary}

        assert by_cat["Refeição"]["total"] == 35.0
        assert by_cat["Refeição"]["count"] == 2
        assert by_cat["Transporte"]["total"] == 25.0
        assert by_cat["Transporte"]["count"] == 1

    def test_filter_by_type(self):
        db.store_transaction(123, "u", "jantar", 20.0, "Refeição", "expense")
        db.store_transaction(123, "u", "salary", 5000.0, "Salário", "income")

        expenses = db.get_summary_by_category(123, *_WIDE_RANGE, "expense")
        income = db.get_summary_by_category(123, *_WIDE_RANGE, "income")

        assert len(expenses) == 1
        assert expenses[0]["category"] == "Refeição"
        assert len(income) == 1
        assert income[0]["category"] == "Salário"

    def test_empty_when_no_data(self):
        summary = db.get_summary_by_category(123, *_WIDE_RANGE)
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
        db.store_transaction(123, "testuser", "jantar", 20.0, "Refeição")
        assert db.get_user_lang(123) == "pt"

    def test_set_and_get_lang(self):
        db.store_transaction(123, "testuser", "jantar", 20.0, "Refeição")
        db.set_lang(123, "en")
        assert db.get_user_lang(123) == "en"

    def test_ensure_user_with_lang(self):
        db.ensure_user_with_lang(500, "languser", "ja")
        assert db.get_user_lang(500) == "ja"

    def test_authenticate_returns_lang(self):
        db.store_transaction(300, "authuser", "jantar", 10.0, "Refeição")
        db.set_password(300, "mypass")
        db.set_lang(300, "en")
        result = db.authenticate_user("authuser", "mypass")
        assert result is not None
        assert result["lang"] == "en"


class TestCategories:
    def test_get_categories_returns_all(self):
        cats = db.get_categories()
        assert len(cats) > 0
        names = {c["name_key"] for c in cats}
        assert "Alimentação" in names
        assert "Salário" in names
        assert "Outros" in names

    def test_get_categories_filter_expense(self):
        cats = db.get_categories("expense")
        for c in cats:
            assert c["type"] == "expense"
        names = {c["name_key"] for c in cats}
        assert "Alimentação" in names
        assert "Salário" not in names

    def test_get_categories_filter_income(self):
        cats = db.get_categories("income")
        for c in cats:
            assert c["type"] == "income"
        names = {c["name_key"] for c in cats}
        assert "Salário" in names
        assert "Alimentação" not in names

    def test_get_category_id(self):
        cat_id = db.get_category_id("Alimentação")
        assert cat_id is not None
        assert isinstance(cat_id, int)

    def test_get_category_id_unknown(self):
        assert db.get_category_id("NonexistentCategory") is None


class TestUserPreferences:
    def test_default_preferences(self):
        db.ensure_user_with_lang(800, "prefuser")
        prefs = db.get_user_preferences(800)
        assert prefs["currency_default"] == "BRL"
        assert prefs["timezone"] == "America/Sao_Paulo"
        assert prefs["confirmation_mode"] == "auto"

    def test_set_preference(self):
        db.ensure_user_with_lang(801, "prefuser2")
        db.set_user_preference(801, "currency_default", "JPY")
        prefs = db.get_user_preferences(801)
        assert prefs["currency_default"] == "JPY"

    def test_set_invalid_key_raises(self):
        db.ensure_user_with_lang(802, "prefuser3")
        with pytest.raises(ValueError, match="Unknown preference key"):
            db.set_user_preference(802, "invalid_key", "value")

    def test_set_timezone(self):
        db.ensure_user_with_lang(803, "tzuser")
        db.set_user_preference(803, "timezone", "Asia/Tokyo")
        prefs = db.get_user_preferences(803)
        assert prefs["timezone"] == "Asia/Tokyo"

    def test_set_currency_default(self):
        db.ensure_user_with_lang(804, "curuser")
        db.set_user_preference(804, "currency_default", "USD")
        prefs = db.get_user_preferences(804)
        assert prefs["currency_default"] == "USD"

    def test_set_confirmation_mode(self):
        db.ensure_user_with_lang(805, "confuser")
        db.set_user_preference(805, "confirmation_mode", "ask")
        prefs = db.get_user_preferences(805)
        assert prefs["confirmation_mode"] == "ask"


class TestCurrencies:
    def test_get_available_currencies(self):
        currencies = db.get_available_currencies()
        codes = {c["code"] for c in currencies}
        assert {"BRL", "USD", "EUR", "JPY", "GBP"} <= codes

    def test_is_valid_currency_true(self):
        assert db.is_valid_currency("BRL") is True
        assert db.is_valid_currency("usd") is True

    def test_is_valid_currency_false(self):
        assert db.is_valid_currency("XYZ") is False

    def test_store_transaction_with_currency(self):
        db.store_transaction(
            900, "curtest", "dinner", 20.0, "Refeição", currency_code="USD",
        )
        txs = db.get_transactions(900, *_WIDE_RANGE)
        assert txs[0]["currency_code"] == "USD"


class TestExchangeRates:
    def test_same_currency_rate(self):
        assert db.get_exchange_rate("USD", "USD") == 1.0
        assert db.get_exchange_rate("BRL", "BRL") == 1.0

    def test_fallback_rate(self):
        rate = db.get_exchange_rate("USD", "BRL")
        assert rate is not None
        assert rate > 0

    def test_store_and_retrieve(self):
        db.store_exchange_rate("USD", "BRL", 5.25)
        rate = db.get_exchange_rate("USD", "BRL")
        assert rate == 5.25

    def test_convert_amount(self):
        db.store_exchange_rate("USD", "BRL", 5.0)
        converted, rate = db.convert_amount(100.0, "USD", "BRL")
        assert converted == 500.0
        assert rate == 5.0

    def test_convert_same_currency(self):
        converted, rate = db.convert_amount(100.0, "BRL", "BRL")
        assert converted == 100.0
        assert rate == 1.0

    def test_store_transaction_with_conversion(self):
        db.store_transaction(
            950, "convtest", "dinner", 30.0, "Refeição",
            currency_code="USD", amount_converted=150.0, exchange_rate=5.0,
        )
        txs = db.get_transactions(950, *_WIDE_RANGE)
        assert txs[0]["currency_code"] == "USD"


class TestRecurringTransactions:
    def test_add_and_list(self):
        db.ensure_user_with_lang(700, "recuser")
        rec_id = db.add_recurring(700, "aluguel", 1500.0, "Moradia", day_of_month=5)
        assert rec_id is not None
        rules = db.get_recurring(700)
        assert len(rules) == 1
        assert rules[0]["description"] == "aluguel"
        assert rules[0]["amount"] == 1500.0
        assert rules[0]["day_of_month"] == 5
        assert rules[0]["active"] == 1

    def test_delete(self):
        db.ensure_user_with_lang(701, "recuser2")
        rec_id = db.add_recurring(701, "netflix", 30.0, "Lazer")
        assert db.delete_recurring(701, rec_id) is True
        assert db.get_recurring(701) == []

    def test_delete_not_found(self):
        assert db.delete_recurring(701, 99999) is False

    def test_delete_wrong_user(self):
        db.ensure_user_with_lang(702, "recuser3")
        rec_id = db.add_recurring(702, "rent", 1500.0, "Moradia")
        assert db.delete_recurring(999, rec_id) is False

    def test_toggle(self):
        db.ensure_user_with_lang(703, "recuser4")
        rec_id = db.add_recurring(703, "gym", 100.0, "Lazer")
        result = db.toggle_recurring(703, rec_id)
        assert result is False
        result = db.toggle_recurring(703, rec_id)
        assert result is True

    def test_toggle_not_found(self):
        assert db.toggle_recurring(703, 99999) is None

    def test_get_due_and_advance(self):
        db.ensure_user_with_lang(704, "recuser5")
        rec_id = db.add_recurring(704, "salary", 5000.0, "Salário", "income", day_of_month=1)
        with db._connect() as conn:
            conn.execute(
                "UPDATE recurring_transactions SET next_run = '2020-01-01' WHERE id = ?",
                (rec_id,),
            )
            conn.commit()
        due = db.get_due_recurring()
        assert any(r["id"] == rec_id for r in due)
        db.advance_recurring(rec_id)
        rules = db.get_recurring(704)
        assert rules[0]["next_run"] > "2020-01-01"

    def test_log_execution(self):
        db.ensure_user_with_lang(705, "recuser6")
        rec_id = db.add_recurring(705, "test", 10.0, "Outros")
        tx_id = db.store_transaction(705, "recuser6", "test", 10.0, "Outros")
        db.log_recurring_execution(rec_id, tx_id)
        with db._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM recurring_logs WHERE recurring_id = ?", (rec_id,)
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["transaction_id"] == tx_id


class TestNLPDatabaseFeatures:
    """Tests for Module 7 DB enhancements (created_at override, confidence, category update)."""

    def test_store_with_created_at_override(self):
        db.ensure_user_with_lang(800, "nlpuser1")
        custom_ts = "2025-03-15T12:00:00+00:00"
        tx_id = db.store_transaction(
            800, "nlpuser1", "jantar", 30.0, "Refeição",
            created_at_override=custom_ts,
        )
        txs = db.get_transactions(800, "2025-01-01T00:00:00", "2025-12-31T23:59:59")
        tx = next(t for t in txs if t["id"] == tx_id)
        assert "2025-03-15" in tx["created_at"]

    def test_store_with_confidence_score(self):
        db.ensure_user_with_lang(801, "nlpuser2")
        tx_id = db.store_transaction(
            801, "nlpuser2", "resturante", 45.0, "Refeição",
            confidence_score=0.85,
        )
        with db._connect() as conn:
            row = conn.execute(
                "SELECT confidence_score FROM transactions WHERE id = ?", (tx_id,)
            ).fetchone()
        assert row["confidence_score"] == 0.85

    def test_store_without_confidence_defaults_null(self):
        db.ensure_user_with_lang(802, "nlpuser3")
        tx_id = db.store_transaction(802, "nlpuser3", "jantar", 30.0, "Refeição")
        with db._connect() as conn:
            row = conn.execute(
                "SELECT confidence_score FROM transactions WHERE id = ?", (tx_id,)
            ).fetchone()
        assert row["confidence_score"] is None

    def test_update_transaction_category(self):
        db.ensure_user_with_lang(803, "nlpuser4")
        tx_id = db.store_transaction(
            803, "nlpuser4", "resturante", 45.0, "Outros",
            confidence_score=0.82,
        )
        assert db.update_transaction_category(803, tx_id, "Refeição") is True
        with db._connect() as conn:
            row = conn.execute(
                "SELECT category, confidence_score FROM transactions WHERE id = ?",
                (tx_id,),
            ).fetchone()
        assert row["category"] == "Refeição"
        assert row["confidence_score"] == 1.0

    def test_update_category_wrong_user(self):
        db.ensure_user_with_lang(804, "nlpuser5")
        tx_id = db.store_transaction(804, "nlpuser5", "test", 10.0, "Outros")
        assert db.update_transaction_category(999, tx_id, "Refeição") is False
