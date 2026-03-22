import hashlib
import os
import secrets
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from utils.i18n import (  # noqa: E402
    LANG_LABELS,
    MONTHS,
    cat_name,
    d,
    fmt_currency,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Finance Dashboard", page_icon="💰", layout="wide")

DB_PATH = os.getenv(
    "DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "data.db"),
)

COLOR_PALETTE = [
    "#4CAF50", "#2196F3", "#FF9800", "#E91E63", "#9C27B0",
    "#00BCD4", "#FF5722", "#607D8B", "#795548",
]


# ---------------------------------------------------------------------------
# Cookie helpers (zero-dependency, uses st.context.cookies + JS)
# ---------------------------------------------------------------------------

_COOKIE_NAME = "finance_session"
_COOKIE_MAX_AGE = 7 * 24 * 3600  # 7 days


def _set_cookie(name: str, value: str, max_age: int = _COOKIE_MAX_AGE) -> None:
    components.html(
        f'<script>document.cookie="{name}={value}; path=/; max-age={max_age}; SameSite=Lax";</script>',
        height=0,
    )


def _delete_cookie(name: str) -> None:
    components.html(
        f'<script>document.cookie="{name}=; path=/; max-age=0; SameSite=Lax";</script>',
        height=0,
    )


def _read_cookie(name: str) -> str | None:
    return st.context.cookies.get(name)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def _verify_hash(password: str, stored_hash: str) -> bool:
    salt, key_hex = stored_hash.split(":", 1)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return secrets.compare_digest(key.hex(), key_hex)


def _db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def verify_login(username: str, password: str) -> dict | None:
    conn = _db_conn()
    row = conn.execute(
        "SELECT id, username, password_hash, lang, is_admin FROM users WHERE LOWER(username) = LOWER(?)",
        (username,),
    ).fetchone()
    conn.close()
    if row is None or row["password_hash"] is None:
        return None
    if _verify_hash(password, row["password_hash"]):
        return {
            "id": row["id"], "username": row["username"],
            "lang": row["lang"] or "pt", "is_admin": bool(row["is_admin"]),
        }
    return None


def _create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn = _db_conn()
    conn.execute("UPDATE users SET session_token = ? WHERE id = ?", (token, user_id))
    conn.commit()
    conn.close()
    return token


def _get_user_by_session(token: str) -> dict | None:
    if not token:
        return None
    conn = _db_conn()
    row = conn.execute(
        "SELECT id, username, lang, is_admin FROM users WHERE session_token = ?",
        (token,),
    ).fetchone()
    conn.close()
    if row:
        return {
            "id": row["id"], "username": row["username"],
            "lang": row["lang"] or "pt", "is_admin": bool(row["is_admin"]),
        }
    return None


def _clear_session(user_id: int) -> None:
    conn = _db_conn()
    conn.execute("UPDATE users SET session_token = NULL WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def _save_lang(user_id: int, lang: str) -> None:
    conn = _db_conn()
    conn.execute("UPDATE users SET lang = ? WHERE id = ?", (lang, user_id))
    conn.commit()
    conn.close()


def show_login_page():
    lang_options = list(LANG_LABELS.values())
    lang_keys = list(LANG_LABELS.keys())

    st.markdown("")
    st.markdown("")
    _, center, _ = st.columns([1, 2, 1])
    with center:
        login_lang_label = st.radio(
            "🌐",
            lang_options,
            horizontal=True,
            label_visibility="collapsed",
        )
        lg = lang_keys[lang_options.index(login_lang_label)]

        st.markdown(f"## {d('login_title', lg)}")
        st.caption(d("login_caption", lg))
        st.markdown("")

        with st.form("login_form"):
            username = st.text_input(d("login_username", lg), placeholder="username")
            password = st.text_input(d("login_password", lg), type="password", placeholder="****")
            submitted = st.form_submit_button(d("login_submit", lg), use_container_width=True)

            if submitted:
                if not username or not password:
                    st.error(d("login_empty", lg))
                else:
                    user = verify_login(username.strip().lstrip("@"), password)
                    if user:
                        token = _create_session(user["id"])
                        _set_cookie(_COOKIE_NAME, token)
                        st.session_state["user"] = user
                        st.rerun()
                    else:
                        st.error(d("login_invalid", lg))


# ---------------------------------------------------------------------------
# Auth gate: check cookie → restore session on refresh
# ---------------------------------------------------------------------------

if "user" not in st.session_state:
    cookie_token = _read_cookie(_COOKIE_NAME)
    if cookie_token:
        restored = _get_user_by_session(cookie_token)
        if restored:
            st.session_state["user"] = restored

if "user" not in st.session_state:
    show_login_page()
    st.stop()

current_user = st.session_state["user"]
user_id: int = current_user["id"]
display_name: str = current_user["username"] or "user"
lang: str = current_user.get("lang", "pt")
_is_admin_user: bool = current_user.get("is_admin", False)


def _fmt(value: float) -> str:
    return fmt_currency(value, lang)


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def _load_admin_user_stats() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT
            u.id,
            u.username,
            u.lang,
            COUNT(a.id) AS total_tx,
            COALESCE(SUM(CASE WHEN COALESCE(a.type,'expense')='expense' THEN a.value ELSE 0 END), 0) AS total_expenses,
            COALESCE(SUM(CASE WHEN a.type='income' THEN a.value ELSE 0 END), 0) AS total_income,
            MIN(a.created_at) AS first_activity,
            MAX(a.created_at) AS last_activity
        FROM users u
        LEFT JOIN actions a ON a.user_id = u.id
        GROUP BY u.id
        ORDER BY last_activity DESC
    """, conn)
    conn.close()
    return df


@st.cache_data(ttl=30)
def _load_admin_daily_stats() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT
            DATE(created_at) AS day,
            COUNT(*) AS tx_count,
            COUNT(DISTINCT user_id) AS active_users,
            SUM(CASE WHEN COALESCE(type,'expense')='expense' THEN value ELSE 0 END) AS expenses,
            SUM(CASE WHEN type='income' THEN value ELSE 0 END) AS income
        FROM actions
        GROUP BY day
        ORDER BY day
    """, conn)
    conn.close()
    if not df.empty:
        df["day"] = pd.to_datetime(df["day"])
    return df


def show_admin_panel() -> None:
    st.title(d("admin_title", lang))

    users_df = _load_admin_user_stats()
    daily_df = _load_admin_daily_stats()

    if users_df.empty:
        st.info(d("admin_no_data", lang))
        return

    total_users = len(users_df)
    d7 = (datetime.now() - timedelta(days=7)).isoformat()
    d30 = (datetime.now() - timedelta(days=30)).isoformat()

    active_7 = int(users_df[
        users_df["last_activity"].notna() & (users_df["last_activity"] >= d7)
    ].shape[0])
    active_30 = int(users_df[
        users_df["last_activity"].notna() & (users_df["last_activity"] >= d30)
    ].shape[0])
    total_tx = int(users_df["total_tx"].sum())

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(d("admin_kpi_users", lang), str(total_users))
    k2.metric(d("admin_kpi_active7", lang), str(active_7))
    k3.metric(d("admin_kpi_active30", lang), str(active_30))
    k4.metric(d("admin_kpi_total_tx", lang), str(total_tx))

    st.markdown("---")

    # Daily activity chart
    if not daily_df.empty:
        r1c1, r1c2 = st.columns(2)

        with r1c1:
            st.subheader(d("admin_chart_daily", lang))
            fig_daily = go.Figure()
            fig_daily.add_trace(go.Bar(
                name=d("type_expense", lang),
                x=daily_df["day"], y=daily_df["expenses"],
                marker_color="#EF5350",
            ))
            fig_daily.add_trace(go.Bar(
                name=d("type_income", lang),
                x=daily_df["day"], y=daily_df["income"],
                marker_color="#4CAF50",
            ))
            fig_daily.update_layout(
                barmode="group",
                xaxis_title="", yaxis_title=d("currency_axis", lang),
                margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend_title_text="",
            )
            st.plotly_chart(fig_daily, use_container_width=True)

        with r1c2:
            st.subheader(d("admin_chart_users", lang))
            fig_users = px.area(
                daily_df, x="day", y="active_users",
                color_discrete_sequence=["#2196F3"],
            )
            fig_users.update_layout(
                xaxis_title="", yaxis_title=d("admin_kpi_users", lang),
                margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_users, use_container_width=True)

    st.markdown("---")

    # Users table
    st.subheader(d("admin_users_table", lang))

    display_df = users_df.copy()
    display_df["balance"] = display_df["total_income"] - display_df["total_expenses"]
    display_df["total_expenses"] = display_df["total_expenses"].apply(_fmt)
    display_df["total_income"] = display_df["total_income"].apply(_fmt)
    display_df["balance"] = display_df["balance"].apply(_fmt)
    for col in ("first_activity", "last_activity"):
        display_df[col] = display_df[col].apply(
            lambda v: v[:16].replace("T", " ") if pd.notna(v) and v else "—"
        )
    display_df = display_df[[
        "username", "lang", "total_tx",
        "total_expenses", "total_income", "balance",
        "first_activity", "last_activity",
    ]]
    display_df.columns = [
        d("admin_col_user", lang), d("admin_col_lang", lang), d("admin_col_tx", lang),
        d("admin_col_expenses", lang), d("admin_col_income", lang), d("admin_col_balance", lang),
        d("admin_col_first", lang), d("admin_col_last", lang),
    ]
    st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)


# ---------------------------------------------------------------------------
# Data loading (all scoped to current user)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def load_actions(_user_id: int, start_iso: str, end_iso: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT a.id, a.action, a.value, a.category,
               COALESCE(a.type, 'expense') AS type, a.created_at
        FROM actions a
        WHERE a.user_id = ? AND a.created_at >= ? AND a.created_at < ?
        ORDER BY a.created_at DESC
        """,
        conn,
        params=[_user_id, start_iso, end_iso],
    )
    conn.close()
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])
        df["date"] = df["created_at"].dt.date
    return df


@st.cache_data(ttl=60)
def load_monthly_totals(_user_id: int) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT strftime('%Y-%m', created_at) AS month,
               SUM(CASE WHEN COALESCE(type,'expense')='expense' THEN value ELSE 0 END) AS expenses,
               SUM(CASE WHEN type='income' THEN value ELSE 0 END) AS income
        FROM actions
        WHERE user_id = ?
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
        """,
        conn,
        params=[_user_id],
    )
    conn.close()
    return df


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.title(f"{display_name}")
st.sidebar.caption(d("sidebar_caption", lang))

lang_options_list = list(LANG_LABELS.values())
lang_keys_list = list(LANG_LABELS.keys())
current_idx = lang_keys_list.index(lang) if lang in lang_keys_list else 0

selected_label = st.sidebar.selectbox(
    d("sidebar_lang", lang),
    lang_options_list,
    index=current_idx,
)
new_lang = lang_keys_list[lang_options_list.index(selected_label)]
if new_lang != lang:
    _save_lang(user_id, new_lang)
    st.session_state["user"]["lang"] = new_lang
    st.rerun()

if st.sidebar.button(d("sidebar_logout", lang), use_container_width=True):
    _clear_session(user_id)
    _delete_cookie(_COOKIE_NAME)
    del st.session_state["user"]
    st.rerun()

if _is_admin_user:
    st.sidebar.markdown("---")
    _view_options = [d("admin_switch_personal", lang), d("admin_switch_admin", lang)]
    _view_default = 1 if st.session_state.get("admin_view", False) else 0
    _selected_view = st.sidebar.radio(
        "🛡️", _view_options, index=_view_default,
        horizontal=True, label_visibility="collapsed",
    )
    _admin_view_active = _selected_view == _view_options[1]
    st.session_state["admin_view"] = _admin_view_active

    if _admin_view_active:
        show_admin_panel()
        _version_file = Path(__file__).resolve().parent.parent / "VERSION"
        _version = _version_file.read_text().strip() if _version_file.exists() else "dev"
        st.sidebar.markdown("---")
        st.sidebar.caption(f"v{_version}")
        st.stop()

st.sidebar.markdown("---")

today = date.today()

# Quick period presets
_QUICK_KEYS = [
    "quick_today", "quick_week", "quick_month", "quick_last_month",
    "quick_3months", "quick_6months", "quick_year", "quick_custom",
]
_quick_labels = [d(k, lang) for k in _QUICK_KEYS]
selected_quick = st.sidebar.radio(
    d("sidebar_quick", lang), _quick_labels, index=2, horizontal=True,
)
_quick_key = _QUICK_KEYS[_quick_labels.index(selected_quick)]


def _month_start(d_: date, months_back: int = 0) -> date:
    m = d_.month - months_back
    y = d_.year
    while m < 1:
        m += 12
        y -= 1
    return date(y, m, 1)


def _month_end(d_: date) -> date:
    nxt = _month_start(d_) + timedelta(days=32)
    return nxt.replace(day=1) - timedelta(days=1)


if _quick_key == "quick_today":
    start_date, end_date = today, today
elif _quick_key == "quick_week":
    start_date = today - timedelta(days=today.weekday())
    end_date = today
elif _quick_key == "quick_month":
    start_date = today.replace(day=1)
    end_date = today
elif _quick_key == "quick_last_month":
    start_date = _month_start(today, 1)
    end_date = _month_end(start_date)
elif _quick_key == "quick_3months":
    start_date = _month_start(today, 2)
    end_date = today
elif _quick_key == "quick_6months":
    start_date = _month_start(today, 5)
    end_date = today
elif _quick_key == "quick_year":
    start_date = date(today.year, 1, 1)
    end_date = today
else:
    start_date = today.replace(day=1)
    end_date = today

if _quick_key == "quick_custom":
    date_range = st.sidebar.date_input(
        d("sidebar_period", lang),
        value=(start_date, end_date),
        max_value=today,
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range

# Compute comparison period (same length, immediately before)
period_days = (end_date - start_date).days + 1
prev_end = start_date - timedelta(days=1)
prev_start = prev_end - timedelta(days=period_days - 1)

start_iso = datetime.combine(start_date, datetime.min.time()).isoformat()
end_iso = datetime.combine(end_date + timedelta(days=1), datetime.min.time()).isoformat()
prev_start_iso = datetime.combine(prev_start, datetime.min.time()).isoformat()
prev_end_iso = datetime.combine(prev_end + timedelta(days=1), datetime.min.time()).isoformat()

df = load_actions(user_id, start_iso, end_iso)
df_prev = load_actions(user_id, prev_start_iso, prev_end_iso)

type_options = [d("type_all", lang), d("type_expense", lang), d("type_income", lang)]
type_keys = ["all", "expense", "income"]
selected_type_label = st.sidebar.radio(d("sidebar_type", lang), type_options, horizontal=True)
selected_type = type_keys[type_options.index(selected_type_label)]

if selected_type != "all":
    if not df.empty:
        df = df[df["type"] == selected_type]
    if not df_prev.empty:
        df_prev = df_prev[df_prev["type"] == selected_type]

if not df.empty:
    df["cat_display"] = df["category"].apply(lambda c: cat_name(c, lang))
    all_internal = sorted(df["category"].unique())
    display_labels = [cat_name(c, lang) for c in all_internal]
    selected_display = st.sidebar.multiselect(
        d("sidebar_categories", lang),
        options=display_labels,
        default=display_labels,
    )
    display_to_internal = dict(zip(display_labels, all_internal))
    selected_internal = {display_to_internal[dl] for dl in selected_display}
    df = df[df["category"].isin(selected_internal)]

st.sidebar.markdown("---")
st.sidebar.markdown(
    f"**{d('sidebar_period_label', lang)}:** {start_date.strftime('%d/%m/%Y')} — {end_date.strftime('%d/%m/%Y')}"
)
if not df.empty:
    st.sidebar.markdown(f"**{d('sidebar_records', lang)}:** {len(df)}")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

months_list = MONTHS.get(lang, MONTHS["pt"])
if start_date.day == 1 and end_date >= today:
    title_period = f"{months_list[today.month]} {today.year}"
else:
    title_period = f"{start_date.strftime('%d/%m')} — {end_date.strftime('%d/%m/%Y')}"

st.title(d("title", lang, period=title_period))

if df.empty:
    st.info(d("no_data", lang))
    st.stop()

# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------

total_expense = df.loc[df["type"] == "expense", "value"].sum() if "type" in df.columns else df["value"].sum()
total_income = df.loc[df["type"] == "income", "value"].sum() if "type" in df.columns else 0.0
balance = total_income - total_expense
tx_count = len(df)

_has_prev = not df_prev.empty and "type" in df_prev.columns
prev_expense = df_prev.loc[df_prev["type"] == "expense", "value"].sum() if _has_prev else 0.0
prev_income = df_prev.loc[df_prev["type"] == "income", "value"].sum() if _has_prev else 0.0
prev_balance = prev_income - prev_expense
prev_tx = len(df_prev) if not df_prev.empty else 0


def _delta_str(current: float, previous: float, invert: bool = False) -> str | None:
    if previous == 0:
        return None
    diff = current - previous
    pct = (diff / previous) * 100
    sign_ch = "+" if diff >= 0 else ""
    return f"{sign_ch}{pct:.0f}%"


k1, k2, k3, k4 = st.columns(4)
k1.metric(
    d("kpi_total", lang), _fmt(total_expense),
    delta=_delta_str(total_expense, prev_expense),
    delta_color="inverse",
)
k2.metric(
    d("kpi_income", lang), _fmt(total_income),
    delta=_delta_str(total_income, prev_income),
    delta_color="normal",
)
bal_sign = "+" if balance >= 0 else "-"
k3.metric(
    d("kpi_balance", lang), f"{bal_sign}{_fmt(abs(balance))}",
    delta=_delta_str(balance, prev_balance) if prev_balance != 0 else None,
    delta_color="normal",
)
k4.metric(
    d("kpi_tx", lang), str(tx_count),
    delta=_delta_str(tx_count, prev_tx),
    delta_color="off",
)

st.markdown("---")

# ---------------------------------------------------------------------------
# Row 1: Spending over time + Category donut
# ---------------------------------------------------------------------------

col_date = d("col_datetime", lang)
col_value = d("col_value", lang)
col_category = d("col_category", lang)

r1c1, r1c2 = st.columns([3, 2])

with r1c1:
    st.subheader(d("chart_timeline", lang))
    type_label = d("col_type", lang)
    type_map = {"expense": d("type_expense", lang), "income": d("type_income", lang)}
    df_timeline = df.copy()
    df_timeline["type_label"] = df_timeline["type"].map(type_map).fillna(d("type_expense", lang))
    daily = df_timeline.groupby(["date", "type_label"])["value"].sum().reset_index()
    daily.columns = [col_date, type_label, col_value]

    color_map = {d("type_expense", lang): "#EF5350", d("type_income", lang): "#4CAF50"}
    fig = px.bar(
        daily, x=col_date, y=col_value, color=type_label,
        color_discrete_map=color_map, barmode="group",
    )
    fig.update_layout(
        yaxis_title=d("currency_axis", lang),
        xaxis_title="",
        hovermode="x unified",
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title_text="",
    )
    fig.update_traces(hovertemplate="%{y:,.2f}<extra></extra>")
    st.plotly_chart(fig, use_container_width=True)

with r1c2:
    st.subheader(d("chart_donut", lang))
    cat_totals = df.groupby("cat_display")["value"].sum().reset_index()
    cat_totals.columns = [col_category, "Total"]
    cat_totals = cat_totals.sort_values("Total", ascending=False)

    fig = px.pie(
        cat_totals,
        values="Total",
        names=col_category,
        hole=0.45,
        color_discrete_sequence=COLOR_PALETTE,
    )
    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        hovertemplate="%{label}: %{value:,.2f}<extra></extra>",
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Row 2: Category bar + Cumulative line
# ---------------------------------------------------------------------------

r2c1, r2c2 = st.columns(2)

with r2c1:
    st.subheader(d("chart_bar", lang))
    cat_sorted = cat_totals.sort_values("Total", ascending=True)

    fig = px.bar(
        cat_sorted,
        x="Total",
        y=col_category,
        orientation="h",
        color=col_category,
        color_discrete_sequence=COLOR_PALETTE,
        text=cat_sorted["Total"].apply(lambda v: _fmt(v)),
    )
    fig.update_layout(
        xaxis_title=d("currency_axis", lang),
        yaxis_title="",
        showlegend=False,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

with r2c2:
    st.subheader(d("chart_cumulative", lang))
    cumulative = df.sort_values("created_at").copy()
    cumulative["signed"] = cumulative.apply(
        lambda r: r["value"] if r["type"] == "income" else -r["value"], axis=1,
    )
    cumulative["cumsum"] = cumulative["signed"].cumsum()

    fig = px.area(
        cumulative,
        x="created_at",
        y="cumsum",
        color_discrete_sequence=["#2196F3"],
    )
    fig.update_layout(
        yaxis_title=d("cumulative_axis", lang),
        xaxis_title="",
        hovermode="x unified",
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_traces(hovertemplate="%{y:,.2f}<extra></extra>")
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Row 3: Period-over-period comparison
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader(d("comparison_title", lang))
st.caption(d("prev_period", lang, start=prev_start.strftime("%d/%m/%Y"), end=prev_end.strftime("%d/%m/%Y")))

if not df_prev.empty:
    cur_label = d("current_period_label", lang)
    prv_label = d("previous_period_label", lang)

    metrics = [
        (d("delta_expenses", lang), total_expense, prev_expense),
        (d("delta_income", lang), total_income, prev_income),
        (d("delta_balance", lang), balance, prev_balance),
    ]
    fig_cmp = go.Figure()
    labels = [m[0] for m in metrics]
    fig_cmp.add_trace(go.Bar(
        name=cur_label, x=labels, y=[m[1] for m in metrics],
        marker_color="#2196F3",
        text=[_fmt(m[1]) for m in metrics], textposition="outside",
    ))
    fig_cmp.add_trace(go.Bar(
        name=prv_label, x=labels, y=[m[2] for m in metrics],
        marker_color="#90A4AE",
        text=[_fmt(m[2]) for m in metrics], textposition="outside",
    ))
    fig_cmp.update_layout(
        barmode="group",
        xaxis_title="", yaxis_title=d("currency_axis", lang),
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title_text="",
    )
    st.plotly_chart(fig_cmp, use_container_width=True)
else:
    st.info(d("no_prev_data", lang))

# ---------------------------------------------------------------------------
# Row 4: Monthly comparison (full history)
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader(d("chart_monthly", lang))

monthly = load_monthly_totals(user_id)
if not monthly.empty:
    monthly = monthly.sort_values("month")
    monthly["label"] = monthly["month"].apply(
        lambda m: f"{months_list[int(m.split('-')[1])]} {m.split('-')[0]}"
    )
    fig_m = go.Figure()
    fig_m.add_trace(go.Bar(
        name=d("type_expense", lang), x=monthly["label"], y=monthly["expenses"],
        marker_color="#EF5350",
        text=monthly["expenses"].apply(lambda v: _fmt(v)),
        textposition="outside",
    ))
    fig_m.add_trace(go.Bar(
        name=d("type_income", lang), x=monthly["label"], y=monthly["income"],
        marker_color="#4CAF50",
        text=monthly["income"].apply(lambda v: _fmt(v)),
        textposition="outside",
    ))
    fig_m.update_layout(
        barmode="group",
        xaxis_title="",
        yaxis_title=d("currency_axis", lang),
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title_text="",
    )
    st.plotly_chart(fig_m, use_container_width=True)
else:
    st.info(d("chart_no_history", lang))

# ---------------------------------------------------------------------------
# Top expenses
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader(d("top_expenses", lang))

top_n = min(10, len(df))
top_expenses = df.nlargest(top_n, "value")[["id", "created_at", "type", "action", "value", "cat_display"]].copy()
type_display_map = {"expense": d("type_expense", lang), "income": d("type_income", lang)}
top_expenses["type"] = top_expenses["type"].map(type_display_map).fillna(d("type_expense", lang))
top_expenses["value"] = top_expenses["value"].apply(lambda v: _fmt(v))
top_expenses["created_at"] = top_expenses["created_at"].dt.strftime("%d/%m/%Y %H:%M")
top_expenses.columns = [
    d("col_id", lang), d("col_datetime", lang), d("col_type", lang),
    d("col_desc", lang), d("col_value", lang), d("col_category", lang),
]
st.dataframe(top_expenses, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Full transaction log
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader(d("all_tx", lang))

search = st.text_input(d("search", lang), "")

display = df.copy()
if search:
    display = display[display["action"].str.contains(search, case=False, na=False)]

display = display[["id", "created_at", "type", "action", "value", "cat_display"]].copy()
display["type"] = display["type"].map(type_display_map).fillna(d("type_expense", lang))
display["value"] = display["value"].apply(lambda v: _fmt(v))
display["created_at"] = display["created_at"].dt.strftime("%d/%m/%Y %H:%M")
display.columns = [
    d("col_id", lang), d("col_datetime", lang), d("col_type", lang),
    d("col_desc", lang), d("col_value", lang), d("col_category", lang),
]

st.dataframe(display, use_container_width=True, hide_index=True, height=400)

st.caption(d("showing", lang, shown=len(display), total=len(df)))

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

_version_file = Path(__file__).resolve().parent.parent / "VERSION"
_version = _version_file.read_text().strip() if _version_file.exists() else "dev"
st.sidebar.markdown("---")
st.sidebar.caption(f"v{_version}")
