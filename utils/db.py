import sqlite3
from pathlib import Path


def _db_path() -> str:
    """
    Return an absolute path to data/data.db regardless of current working directory.
    """
    # utils/ -> project root -> data/data.db
    project_root = Path(__file__).resolve().parent.parent
    return str(project_root / "data" / "data.db")

# Database setup
def setup_database():
    with sqlite3.connect(_db_path()) as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                value REAL NOT NULL
            )
            '''
        )
        conn.commit()

# Function to store data in the database
def store_data(action, value):
    with sqlite3.connect(_db_path()) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO actions (action, value) VALUES (?, ?)', (action, value))
        conn.commit()