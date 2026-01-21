import sqlite3
from pathlib import Path
import datetime


def _db_path() -> str:
    """
    Return an absolute path to data/data.db regardless of current working directory.
    """
    # utils/ -> project root -> data/data.db
    project_root = Path(__file__).resolve().parent.parent
    return str(project_root / "data" / "data.db")


def _connect():
    conn = sqlite3.connect(_db_path())
    # Enable FK constraints (SQLite requires this per-connection)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    return {r[1] for r in rows}  # second column is name


# Database setup
def setup_database():
    with _connect() as conn:
        cursor = conn.cursor()

        # Users table (id = Telegram user id)
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT
            )
            '''
        )

        # App lifecycle events (one row when the app starts, etc.)
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS app_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            '''
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_app_events_created_at ON app_events(created_at);")

        # High-level usage log (does NOT store message contents)
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            '''
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_events_user_id ON usage_events(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_events_created_at ON usage_events(created_at);")

        # Actions table (new schema includes user_id FK)
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                value REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            '''
        )

        # Lightweight migration for older DBs: add user_id column if missing
        cols = _table_columns(conn, "actions")
        if "user_id" not in cols:
            cursor.execute("ALTER TABLE actions ADD COLUMN user_id INTEGER;")

        # Migration: add created_at column if missing (backfill existing rows)
        cols = _table_columns(conn, "actions")
        if "created_at" not in cols:
            cursor.execute("ALTER TABLE actions ADD COLUMN created_at TEXT;")
            cursor.execute("UPDATE actions SET created_at = datetime('now') WHERE created_at IS NULL;")

        # Helpful index for per-user queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_user_id ON actions(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_created_at ON actions(created_at);")

        conn.commit()


def ensure_user(user_id: int, username: str | None) -> None:
    """
    Create/update a user row.

    - user_id: Telegram numeric user id
    - username: Telegram username (may be None)
    """
    with _connect() as conn:
        conn.execute(
            '''
            INSERT INTO users (id, username)
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = COALESCE(excluded.username, users.username)
            ''',
            (user_id, username),
        )
        conn.commit()

def log_app_event(event_type: str) -> None:
    """
    Log an app lifecycle event (e.g., "app_started").
    """
    created_at = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO app_events (event_type, created_at) VALUES (?, ?)",
            (event_type, created_at),
        )
        conn.commit()

def log_usage(user_id: int, username: str | None, event_type: str) -> None:
    """
    Log high-level bot usage without storing message specifics.

    Examples of event_type: "action_stored"
    """
    ensure_user(user_id, username)
    created_at = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO usage_events (user_id, event_type, created_at) VALUES (?, ?, ?)",
            (user_id, event_type, created_at),
        )
        conn.commit()

def store_action(user_id: int, username: str | None, action: str, value: float) -> None:
    """
    Store an action for a given Telegram user.
    """
    ensure_user(user_id, username)
    with _connect() as conn:
        created_at = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()
        conn.execute(
            "INSERT INTO actions (user_id, action, value, created_at) VALUES (?, ?, ?, ?)",
            (user_id, action, value, created_at),
        )
        conn.commit()


def store_data(action, value):
    """
    Backwards-compatible insert (no user attached).
    """
    with _connect() as conn:
        created_at = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()
        conn.execute(
            "INSERT INTO actions (user_id, action, value, created_at) VALUES (?, ?, ?, ?)",
            (None, action, value, created_at),
        )
        conn.commit()