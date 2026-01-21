import sqlite3

# Database setup
def setup_database():
    conn = sqlite3.connect('../data/data.db')  # Adjust path to match folder structure
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            value REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Function to store data in the database
def store_data(action, value):
    conn = sqlite3.connect('../data/data.db')  # Adjust path to match folder structure
    cursor = conn.cursor()
    cursor.execute('INSERT INTO actions (action, value) VALUES (?, ?)', (action, value))
    conn.commit()
    conn.close()