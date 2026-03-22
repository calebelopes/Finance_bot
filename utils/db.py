import datetime
import hashlib
import logging
import secrets
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _db_path() -> str:
    project_root = Path(__file__).resolve().parent.parent
    db_dir = project_root / "data"
    db_dir.mkdir(exist_ok=True)
    return str(db_dir / "data.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    return {r["name"] for r in rows}


# ---------------------------------------------------------------------------
# Schema & migrations
# ---------------------------------------------------------------------------

def setup_database() -> None:
    with _connect() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY,
                username TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_app_events_created_at ON app_events(created_at);"
        )

        cur.execute("""
            CREATE TABLE IF NOT EXISTS usage_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_user_id ON usage_events(user_id);"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_events_created_at ON usage_events(created_at);"
        )

        cur.execute("""
            CREATE TABLE IF NOT EXISTS actions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                action     TEXT    NOT NULL,
                value      REAL    NOT NULL,
                category   TEXT    NOT NULL DEFAULT 'Outros',
                created_at TEXT    NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Lightweight migrations for older databases
        user_cols = _table_columns(conn, "users")
        if "password_hash" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN password_hash TEXT;")
        if "lang" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'pt';")
        if "session_token" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN session_token TEXT;")
        if "is_admin" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0;")

        cols = _table_columns(conn, "actions")
        if "user_id" not in cols:
            cur.execute("ALTER TABLE actions ADD COLUMN user_id INTEGER;")
        if "created_at" not in cols:
            cur.execute("ALTER TABLE actions ADD COLUMN created_at TEXT;")
            cur.execute("UPDATE actions SET created_at = datetime('now') WHERE created_at IS NULL;")
        if "category" not in cols:
            cur.execute("ALTER TABLE actions ADD COLUMN category TEXT NOT NULL DEFAULT 'Outros';")
        if "type" not in cols:
            cur.execute("ALTER TABLE actions ADD COLUMN type TEXT NOT NULL DEFAULT 'expense';")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_actions_user_id    ON actions(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_actions_created_at ON actions(created_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_actions_category   ON actions(category);")

        conn.commit()
        log.info("Database ready at %s", _db_path())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_user(conn: sqlite3.Connection, user_id: int, username: str | None, lang: str | None = None) -> None:
    if lang:
        conn.execute(
            """
            INSERT INTO users (id, username, lang) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = COALESCE(excluded.username, users.username),
                lang = COALESCE(excluded.lang, users.lang)
            """,
            (user_id, username, lang),
        )
    else:
        conn.execute(
            """
            INSERT INTO users (id, username) VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = COALESCE(excluded.username, users.username)
            """,
            (user_id, username),
        )


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def store_action(
    user_id: int,
    username: str | None,
    action: str,
    value: float,
    category: str,
    action_type: str = "expense",
) -> int:
    """
    Atomically: upsert user, insert action, log usage event.
    Returns the new action row id.
    """
    with _connect() as conn:
        _ensure_user(conn, user_id, username)
        created_at = _utc_now()
        cur = conn.execute(
            "INSERT INTO actions (user_id, action, value, category, type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, action, value, category, action_type, created_at),
        )
        action_id = cur.lastrowid
        conn.execute(
            "INSERT INTO usage_events (user_id, event_type, created_at) VALUES (?, ?, ?)",
            (user_id, "action_stored", created_at),
        )
        conn.commit()
    return action_id


def log_app_event(event_type: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO app_events (event_type, created_at) VALUES (?, ?)",
            (event_type, _utc_now()),
        )
        conn.commit()


def delete_action(user_id: int, action_id: int) -> bool:
    """Delete an action only if it belongs to *user_id*. Returns True on success."""
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM actions WHERE id = ? AND user_id = ?",
            (action_id, user_id),
        )
        conn.commit()
    return cur.rowcount > 0


def edit_action_value(user_id: int, action_id: int, new_value: float) -> bool:
    """Update the value of an action only if it belongs to *user_id*."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE actions SET value = ? WHERE id = ? AND user_id = ?",
            (new_value, action_id, user_id),
        )
        conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_actions(user_id: int, start_utc: str, end_utc: str) -> list[dict]:
    """Return actions for *user_id* where created_at is in [start_utc, end_utc)."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, action, value, category, type, created_at
            FROM actions
            WHERE user_id = ? AND created_at >= ? AND created_at < ?
            ORDER BY created_at ASC
            """,
            (user_id, start_utc, end_utc),
        ).fetchall()
    return [dict(r) for r in rows]


def get_summary_by_category(
    user_id: int, start_utc: str, end_utc: str, action_type: str | None = None,
) -> list[dict]:
    """Return spending grouped by category for *user_id* in the given UTC range."""
    if action_type:
        query = """
            SELECT category, SUM(value) AS total, COUNT(*) AS count
            FROM actions
            WHERE user_id = ? AND created_at >= ? AND created_at < ? AND type = ?
            GROUP BY category
            ORDER BY total DESC
        """
        params = (user_id, start_utc, end_utc, action_type)
    else:
        query = """
            SELECT category, SUM(value) AS total, COUNT(*) AS count
            FROM actions
            WHERE user_id = ? AND created_at >= ? AND created_at < ?
            GROUP BY category
            ORDER BY total DESC
        """
        params = (user_id, start_utc, end_utc)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}:{key.hex()}"


def _verify_password_hash(password: str, stored_hash: str) -> bool:
    salt, key_hex = stored_hash.split(":", 1)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return secrets.compare_digest(key.hex(), key_hex)


def set_password(user_id: int, password: str) -> None:
    """Set or update the dashboard password for a user."""
    hashed = _hash_password(password)
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hashed, user_id),
        )
        conn.commit()


def authenticate_user(username: str, password: str) -> dict | None:
    """
    Verify username + password.
    Returns {"id": ..., "username": ..., "lang": ..., "is_admin": ...} on success, None otherwise.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, lang, is_admin FROM users WHERE LOWER(username) = LOWER(?)",
            (username,),
        ).fetchone()
    if row is None or row["password_hash"] is None:
        return None
    if _verify_password_hash(password, row["password_hash"]):
        return {
            "id": row["id"], "username": row["username"],
            "lang": row["lang"] or "pt", "is_admin": bool(row["is_admin"]),
        }
    return None


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------

def get_user_lang(user_id: int) -> str:
    """Return the stored language preference for a user, defaulting to 'pt'."""
    with _connect() as conn:
        row = conn.execute("SELECT lang FROM users WHERE id = ?", (user_id,)).fetchone()
    if row and row["lang"]:
        return row["lang"]
    return "pt"


def set_lang(user_id: int, lang: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET lang = ? WHERE id = ?", (lang, user_id))
        conn.commit()


def ensure_user_with_lang(user_id: int, username: str | None, lang: str | None = None) -> None:
    """Public wrapper: upsert user and optionally set initial language."""
    with _connect() as conn:
        _ensure_user(conn, user_id, username, lang)
        conn.commit()


# ---------------------------------------------------------------------------
# Sessions (cookie-based persistent login for dashboard)
# ---------------------------------------------------------------------------

def create_session(user_id: int) -> str:
    """Generate a random session token and store it on the user row."""
    token = secrets.token_urlsafe(32)
    with _connect() as conn:
        conn.execute("UPDATE users SET session_token = ? WHERE id = ?", (token, user_id))
        conn.commit()
    return token


def get_user_by_session(token: str) -> dict | None:
    """Look up a user by session token. Returns user dict or None."""
    if not token:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, lang, is_admin FROM users WHERE session_token = ?",
            (token,),
        ).fetchone()
    if row:
        return {
            "id": row["id"], "username": row["username"],
            "lang": row["lang"] or "pt", "is_admin": bool(row["is_admin"]),
        }
    return None


def clear_session(user_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET session_token = NULL WHERE id = ?", (user_id,))
        conn.commit()


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

def set_admin(user_id: int, is_admin: bool = True) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (int(is_admin), user_id))
        conn.commit()


def is_admin(user_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,)).fetchone()
    return bool(row and row["is_admin"])


def get_all_users_stats() -> list[dict]:
    """Return per-user statistics for the admin dashboard."""
    with _connect() as conn:
        rows = conn.execute("""
            SELECT
                u.id,
                u.username,
                u.lang,
                COUNT(a.id) AS total_tx,
                COALESCE(SUM(CASE WHEN a.type='expense' THEN a.value ELSE 0 END), 0) AS total_expenses,
                COALESCE(SUM(CASE WHEN a.type='income' THEN a.value ELSE 0 END), 0) AS total_income,
                MIN(a.created_at) AS first_activity,
                MAX(a.created_at) AS last_activity
            FROM users u
            LEFT JOIN actions a ON a.user_id = u.id
            GROUP BY u.id
            ORDER BY last_activity DESC
        """).fetchall()
    return [dict(r) for r in rows]


def get_platform_daily_stats() -> list[dict]:
    """Return daily transaction counts and totals across all users."""
    with _connect() as conn:
        rows = conn.execute("""
            SELECT
                DATE(created_at) AS day,
                COUNT(*) AS tx_count,
                COUNT(DISTINCT user_id) AS active_users,
                SUM(CASE WHEN COALESCE(type,'expense')='expense' THEN value ELSE 0 END) AS expenses,
                SUM(CASE WHEN type='income' THEN value ELSE 0 END) AS income
            FROM actions
            GROUP BY day
            ORDER BY day
        """).fetchall()
    return [dict(r) for r in rows]
