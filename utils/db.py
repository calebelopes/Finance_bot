import datetime
import hashlib
import logging
import secrets
import sqlite3
from pathlib import Path

from utils.categories import get_all_category_seeds

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


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Schema & migrations
# ---------------------------------------------------------------------------

_CURRENCY_SEEDS = [
    ("BRL", "Brazilian Real", "R$"),
    ("USD", "US Dollar", "$"),
    ("EUR", "Euro", "€"),
    ("JPY", "Japanese Yen", "¥"),
    ("GBP", "British Pound", "£"),
]


def setup_database() -> None:  # noqa: C901
    with _connect() as conn:
        cur = conn.cursor()

        # -- users (unchanged) -----------------------------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY,
                username TEXT
            )
        """)

        user_cols = _table_columns(conn, "users")
        if "password_hash" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN password_hash TEXT;")
        if "lang" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'pt';")
        if "session_token" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN session_token TEXT;")
        if "is_admin" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0;")

        # -- app_events / usage_events (unchanged) ---------------------------
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

        # -- currencies ------------------------------------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS currencies (
                code   TEXT PRIMARY KEY,
                name   TEXT NOT NULL,
                symbol TEXT NOT NULL
            )
        """)
        for code, name, symbol in _CURRENCY_SEEDS:
            cur.execute(
                "INSERT OR IGNORE INTO currencies (code, name, symbol) VALUES (?, ?, ?)",
                (code, name, symbol),
            )

        # -- categories ------------------------------------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name_key   TEXT NOT NULL UNIQUE,
                icon       TEXT,
                type       TEXT NOT NULL DEFAULT 'expense',
                is_system  INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)

        # -- category_aliases ------------------------------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS category_aliases (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL REFERENCES categories(id),
                alias       TEXT NOT NULL,
                lang        TEXT NOT NULL DEFAULT 'pt',
                UNIQUE(alias, lang)
            )
        """)

        # Seed categories + aliases
        now = _utc_now()
        for seed in get_all_category_seeds():
            cur.execute(
                "INSERT OR IGNORE INTO categories (name_key, icon, type, is_system, created_at) "
                "VALUES (?, ?, ?, 1, ?)",
                (seed["name_key"], seed["icon"], seed["type"], now),
            )
            cat_row = cur.execute(
                "SELECT id FROM categories WHERE name_key = ?", (seed["name_key"],)
            ).fetchone()
            if cat_row:
                cat_id = cat_row[0]
                for lang, aliases in seed.get("keywords", {}).items():
                    for alias in aliases:
                        cur.execute(
                            "INSERT OR IGNORE INTO category_aliases (category_id, alias, lang) "
                            "VALUES (?, ?, ?)",
                            (cat_id, alias, lang),
                        )

        # -- exchange_rates --------------------------------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS exchange_rates (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                from_currency TEXT NOT NULL REFERENCES currencies(code),
                to_currency   TEXT NOT NULL REFERENCES currencies(code),
                rate          REAL NOT NULL,
                fetched_at    TEXT NOT NULL
            )
        """)

        # -- user_preferences ------------------------------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id           INTEGER PRIMARY KEY REFERENCES users(id),
                currency_default  TEXT NOT NULL DEFAULT 'BRL' REFERENCES currencies(code),
                timezone          TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
                confirmation_mode TEXT NOT NULL DEFAULT 'auto'
            )
        """)

        # -- recurring_transactions ------------------------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS recurring_transactions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL REFERENCES users(id),
                description   TEXT NOT NULL,
                amount        REAL NOT NULL,
                currency_code TEXT NOT NULL DEFAULT 'BRL' REFERENCES currencies(code),
                category_id   INTEGER REFERENCES categories(id),
                type          TEXT NOT NULL DEFAULT 'expense',
                frequency     TEXT NOT NULL DEFAULT 'monthly',
                day_of_month  INTEGER,
                next_run      TEXT,
                active        INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT NOT NULL
            )
        """)

        # -- recurring_logs --------------------------------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS recurring_logs (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                recurring_id   INTEGER NOT NULL REFERENCES recurring_transactions(id),
                transaction_id INTEGER,
                executed_at    TEXT NOT NULL
            )
        """)

        # ================================================================
        # Migrate actions → transactions
        # ================================================================

        has_actions = _table_exists(conn, "actions")
        has_transactions = _table_exists(conn, "transactions")

        if has_actions and not has_transactions:
            cur.execute("ALTER TABLE actions RENAME TO transactions;")
            log.info("Renamed table actions → transactions")
            has_transactions = True

        if not has_transactions:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id          INTEGER REFERENCES users(id),
                    description      TEXT    NOT NULL,
                    amount_original  REAL    NOT NULL,
                    currency_code    TEXT    NOT NULL DEFAULT 'BRL',
                    amount_converted REAL,
                    exchange_rate    REAL,
                    category         TEXT    NOT NULL DEFAULT 'Outros',
                    category_id      INTEGER REFERENCES categories(id),
                    type             TEXT    NOT NULL DEFAULT 'expense',
                    source           TEXT    NOT NULL DEFAULT 'text',
                    status           TEXT    NOT NULL DEFAULT 'confirmed',
                    confidence_score REAL,
                    recurring_id     INTEGER REFERENCES recurring_transactions(id),
                    created_at       TEXT    NOT NULL,
                    FOREIGN KEY (currency_code) REFERENCES currencies(code)
                )
            """)

        # Column renames (for databases migrated from actions)
        tx_cols = _table_columns(conn, "transactions")

        if "action" in tx_cols and "description" not in tx_cols:
            cur.execute("ALTER TABLE transactions RENAME COLUMN action TO description;")
            log.info("Renamed column action → description")

        if "value" in tx_cols and "amount_original" not in tx_cols:
            cur.execute("ALTER TABLE transactions RENAME COLUMN value TO amount_original;")
            log.info("Renamed column value → amount_original")

        # Refresh after renames
        tx_cols = _table_columns(conn, "transactions")

        # Add missing columns for migrated databases
        _new_cols = {
            "user_id": "INTEGER",
            "created_at": "TEXT",
            "category": "TEXT NOT NULL DEFAULT 'Outros'",
            "type": "TEXT NOT NULL DEFAULT 'expense'",
            "currency_code": "TEXT NOT NULL DEFAULT 'BRL'",
            "amount_converted": "REAL",
            "exchange_rate": "REAL",
            "source": "TEXT NOT NULL DEFAULT 'text'",
            "status": "TEXT NOT NULL DEFAULT 'confirmed'",
            "confidence_score": "REAL",
            "recurring_id": "INTEGER",
            "category_id": "INTEGER",
        }
        for col, typedef in _new_cols.items():
            if col not in tx_cols:
                cur.execute(f"ALTER TABLE transactions ADD COLUMN {col} {typedef};")
                log.info("Added column transactions.%s", col)

        # Backfill created_at for very old rows
        cur.execute(
            "UPDATE transactions SET created_at = datetime('now') WHERE created_at IS NULL;"
        )

        # Backfill category_id from category text
        cur.execute("""
            UPDATE transactions
            SET category_id = (SELECT c.id FROM categories c WHERE c.name_key = transactions.category)
            WHERE category_id IS NULL AND category IS NOT NULL
        """)

        # Indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_user_id    ON transactions(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_created_at ON transactions(created_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_category   ON transactions(category);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_cat_id     ON transactions(category_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_status     ON transactions(status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_type       ON transactions(type);")

        # Create user_preferences for existing users that lack one
        cur.execute("""
            INSERT OR IGNORE INTO user_preferences (user_id)
            SELECT id FROM users
            WHERE id NOT IN (SELECT user_id FROM user_preferences)
        """)

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

def store_transaction(
    user_id: int,
    username: str | None,
    description: str,
    amount: float,
    category: str,
    action_type: str = "expense",
    currency_code: str = "BRL",
    source: str = "text",
    category_id: int | None = None,
) -> int:
    """Atomically: upsert user, insert transaction, log usage event. Returns the new row id."""
    with _connect() as conn:
        _ensure_user(conn, user_id, username)
        created_at = _utc_now()

        if category_id is None:
            row = conn.execute(
                "SELECT id FROM categories WHERE name_key = ?", (category,)
            ).fetchone()
            if row:
                category_id = row["id"]

        cur = conn.execute(
            """INSERT INTO transactions
               (user_id, description, amount_original, currency_code, category, category_id,
                type, source, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', ?)""",
            (user_id, description, amount, currency_code, category, category_id,
             action_type, source, created_at),
        )
        tx_id = cur.lastrowid
        conn.execute(
            "INSERT INTO usage_events (user_id, event_type, created_at) VALUES (?, ?, ?)",
            (user_id, "action_stored", created_at),
        )
        conn.commit()
    return tx_id


def log_app_event(event_type: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO app_events (event_type, created_at) VALUES (?, ?)",
            (event_type, _utc_now()),
        )
        conn.commit()


def delete_transaction(user_id: int, tx_id: int) -> bool:
    """Delete a transaction only if it belongs to *user_id*. Returns True on success."""
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM transactions WHERE id = ? AND user_id = ?",
            (tx_id, user_id),
        )
        conn.commit()
    return cur.rowcount > 0


def edit_transaction(user_id: int, tx_id: int, new_amount: float) -> bool:
    """Update the amount of a transaction only if it belongs to *user_id*."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE transactions SET amount_original = ? WHERE id = ? AND user_id = ?",
            (new_amount, tx_id, user_id),
        )
        conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_transactions(user_id: int, start_utc: str, end_utc: str) -> list[dict]:
    """Return transactions for *user_id* where created_at is in [start_utc, end_utc)."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, description, amount_original, category, category_id, type,
                   currency_code, source, status, created_at
            FROM transactions
            WHERE user_id = ? AND created_at >= ? AND created_at < ?
              AND status != 'deleted'
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
            SELECT category, SUM(amount_original) AS total, COUNT(*) AS count
            FROM transactions
            WHERE user_id = ? AND created_at >= ? AND created_at < ?
              AND type = ? AND status != 'deleted'
            GROUP BY category
            ORDER BY total DESC
        """
        params = (user_id, start_utc, end_utc, action_type)
    else:
        query = """
            SELECT category, SUM(amount_original) AS total, COUNT(*) AS count
            FROM transactions
            WHERE user_id = ? AND created_at >= ? AND created_at < ?
              AND status != 'deleted'
            GROUP BY category
            ORDER BY total DESC
        """
        params = (user_id, start_utc, end_utc)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

def get_categories(cat_type: str | None = None) -> list[dict]:
    """Return all categories, optionally filtered by type ('expense'/'income')."""
    with _connect() as conn:
        if cat_type:
            rows = conn.execute(
                "SELECT id, name_key, icon, type FROM categories WHERE type = ? ORDER BY name_key",
                (cat_type,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, name_key, icon, type FROM categories ORDER BY name_key"
            ).fetchall()
    return [dict(r) for r in rows]


def get_category_id(name_key: str) -> int | None:
    """Look up a category's id by its name_key."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM categories WHERE name_key = ?", (name_key,)
        ).fetchone()
    return row["id"] if row else None


# ---------------------------------------------------------------------------
# Currencies
# ---------------------------------------------------------------------------

def get_available_currencies() -> list[dict]:
    """Return all supported currencies."""
    with _connect() as conn:
        rows = conn.execute("SELECT code, name, symbol FROM currencies ORDER BY code").fetchall()
    return [dict(r) for r in rows]


def is_valid_currency(code: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM currencies WHERE code = ?", (code.upper(),)).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# User preferences
# ---------------------------------------------------------------------------

def get_user_preferences(user_id: int) -> dict:
    """Return preferences for user, creating defaults if missing."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            return dict(row)
        conn.execute("INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)", (user_id,))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)
        ).fetchone()
    return dict(row)


def set_user_preference(user_id: int, key: str, value: str) -> None:
    """Update a single preference. Key must be a valid column name."""
    allowed = {"currency_default", "timezone", "confirmation_mode"}
    if key not in allowed:
        raise ValueError(f"Unknown preference key: {key}")
    with _connect() as conn:
        conn.execute("INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)", (user_id,))
        conn.execute(f"UPDATE user_preferences SET {key} = ? WHERE user_id = ?", (value, user_id))
        conn.commit()


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
    """Verify username + password. Returns user dict on success, None otherwise."""
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
                COUNT(t.id) AS total_tx,
                COALESCE(SUM(CASE WHEN t.type='expense' THEN t.amount_original ELSE 0 END), 0)
                    AS total_expenses,
                COALESCE(SUM(CASE WHEN t.type='income' THEN t.amount_original ELSE 0 END), 0)
                    AS total_income,
                MIN(t.created_at) AS first_activity,
                MAX(t.created_at) AS last_activity
            FROM users u
            LEFT JOIN transactions t ON t.user_id = u.id AND t.status != 'deleted'
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
                SUM(CASE WHEN COALESCE(type,'expense')='expense' THEN amount_original ELSE 0 END)
                    AS expenses,
                SUM(CASE WHEN type='income' THEN amount_original ELSE 0 END) AS income
            FROM transactions
            WHERE status != 'deleted'
            GROUP BY day
            ORDER BY day
        """).fetchall()
    return [dict(r) for r in rows]
