"""Phase 4 tests: dashboard rendering, period filtering, charts payload, exports."""

import datetime
import json
import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from utils import db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db_file = str(tmp_path / "phase4.db")
    with patch.object(db, "_db_path", return_value=db_file):
        db.setup_database()
        from web import main as web_main  # noqa: PLC0415
        client = TestClient(web_main.app)
        uid = db.create_web_user("alice", "secret123", email="alice@example.com")
        token = db.create_session(uid)
        client.cookies.set("finance_session", token)
        # Seed a few transactions in the *current* month
        # We use today's date so the default 'month' period catches them.
        now = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()
        db.store_transaction(uid, "alice", "jantar", 30.0, "Refeição", "expense",
                             created_at_override=now)
        db.store_transaction(uid, "alice", "uber", 15.0, "Transporte", "expense",
                             created_at_override=now)
        db.store_transaction(uid, "alice", "salario", 5000.0, "Salário", "income",
                             created_at_override=now)
        yield client, uid


def _chart_data(html: str) -> dict:
    m = re.search(r'<script id="chart-data" type="application/json">\s*(\{.*?\})\s*</script>',
                  html, re.DOTALL)
    assert m is not None, "chart-data script not found"
    return json.loads(m.group(1))


class TestDashboardView:
    def test_dashboard_renders(self, fresh_db):
        client, _ = fresh_db
        r = client.get("/dashboard")
        assert r.status_code == 200
        assert "chart-timeline" in r.text
        assert "chart-donut" in r.text
        assert "chart-bar" in r.text
        assert "chart-cumulative" in r.text

    def test_dashboard_kpis_correct(self, fresh_db):
        client, _ = fresh_db
        r = client.get("/dashboard")
        assert r.status_code == 200
        # Total expense = 45,00 (30 + 15)
        assert "45,00" in r.text or "45.00" in r.text
        # Total income = 5000
        assert "5.000,00" in r.text or "5,000.00" in r.text

    def test_dashboard_redirects_anonymous(self, fresh_db):
        client, _ = fresh_db
        client.cookies.clear()
        r = client.get("/dashboard", follow_redirects=False)
        assert r.status_code == 303

    def test_dashboard_invalid_period_falls_back(self, fresh_db):
        client, _ = fresh_db
        r = client.get("/dashboard?period=bogus")
        assert r.status_code == 200

    def test_dashboard_type_filter_expense(self, fresh_db):
        client, _ = fresh_db
        r = client.get("/dashboard?type=expense")
        assert r.status_code == 200
        # Income transaction "salario" should NOT appear in the table
        # (but might still be in chart data if we filtered)
        assert "salario" not in r.text or r.text.count("salario") < 2

    def test_dashboard_search_filters_table(self, fresh_db):
        client, _ = fresh_db
        r = client.get("/dashboard?search=jantar")
        assert r.status_code == 200
        assert "jantar" in r.text
        # uber/salario shouldn't appear in table (only in charts)
        # We can check the table count
        assert "Mostrando 1" in r.text or "Showing 1" in r.text or "1件中" in r.text

    def test_custom_period(self, fresh_db):
        client, _ = fresh_db
        today = datetime.date.today().isoformat()
        r = client.get(
            f"/dashboard?period=custom&custom_start={today}&custom_end={today}",
        )
        assert r.status_code == 200


class TestChartPayload:
    def test_timeline_chart_present(self, fresh_db):
        client, _ = fresh_db
        r = client.get("/dashboard")
        data = _chart_data(r.text)
        assert "timeline" in data
        assert "data" in data["timeline"]
        # Two traces (expense + income)
        assert len(data["timeline"]["data"]) == 2

    def test_donut_has_categories(self, fresh_db):
        client, _ = fresh_db
        r = client.get("/dashboard")
        data = _chart_data(r.text)
        labels = data["donut"]["data"][0]["labels"]
        # We have Refeição, Transporte, Salário (or translated)
        assert len(labels) == 3

    def test_cumulative_increases_then_recovers(self, fresh_db):
        client, _ = fresh_db
        r = client.get("/dashboard")
        data = _chart_data(r.text)
        ys = data["cumulative"]["data"][0]["y"]
        # Three transactions → three points
        assert len(ys) == 3
        # Final cumulative = -30 -15 +5000 = 4955
        assert ys[-1] == pytest.approx(4955.0)

    def test_no_data_returns_no_charts_block(self, fresh_db):
        client, uid = fresh_db
        # Query a period with no data: yesterday-only
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        r = client.get(
            f"/dashboard?period=custom&custom_start={yesterday}&custom_end={yesterday}",
        )
        assert r.status_code == 200
        # The page renders, but no chart-data block should be embedded
        assert 'id="chart-data"' not in r.text


class TestExports:
    def test_export_csv(self, fresh_db):
        client, _ = fresh_db
        r = client.get("/dashboard/export.csv")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        body = r.content.decode("utf-8-sig")
        assert "jantar" in body
        assert "uber" in body
        assert "salario" in body

    def test_export_pdf(self, fresh_db):
        client, _ = fresh_db
        r = client.get("/dashboard/export.pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        # PDF binary starts with %PDF
        assert r.content[:4] == b"%PDF"

    def test_export_csv_requires_login(self, fresh_db):
        client, _ = fresh_db
        client.cookies.clear()
        r = client.get("/dashboard/export.csv", follow_redirects=False)
        assert r.status_code == 303


class TestPeriodHelpers:
    def test_resolve_period_today(self, fresh_db):
        from web.period import resolve_period
        _, uid = fresh_db
        s, e = resolve_period(uid, "today")
        today = datetime.date.today()
        assert s == today
        assert e == today

    def test_resolve_period_month_starts_first(self, fresh_db):
        from web.period import resolve_period
        _, uid = fresh_db
        s, _ = resolve_period(uid, "month")
        assert s.day == 1

    def test_previous_range_same_length(self, fresh_db):
        from web.period import previous_range
        s = datetime.date(2025, 1, 5)
        e = datetime.date(2025, 1, 10)
        ps, pe = previous_range(s, e)
        assert pe == datetime.date(2025, 1, 4)
        assert (e - s).days == (pe - ps).days
