import sqlite3
from pathlib import Path

from app.config import DATABASE_PATH


class DatabaseManager:

    def __init__(self):
        self.db_path: Path = DATABASE_PATH

        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row

        self.cursor = self.connection.cursor()

        self.create_tables()

    def create_tables(self):

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins(
            username TEXT PRIMARY KEY,
            role TEXT NOT NULL
        )
        """)

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups_list(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER UNIQUE,
            title TEXT NOT NULL
        )
        """)

        self.connection.commit()

    # =====================================================
    # SETTINGS
    # =====================================================

    def set_setting(self, key: str, value: str):

        self.cursor.execute("""
        INSERT OR REPLACE INTO settings(key, value)
        VALUES (?, ?)
        """, (key, str(value)))

        self.connection.commit()

    def get_setting(self, key: str):

        self.cursor.execute("""
        SELECT value
        FROM settings
        WHERE key = ?
        """, (key,))

        row = self.cursor.fetchone()

        if row:
            return row["value"]

        return None

    # =====================================================
    # ADMINS
    # =====================================================

    def add_admin(self, username, role="admin"):

        username = username.lower()

        self.cursor.execute("""
        INSERT OR REPLACE INTO admins(username, role)
        VALUES (?, ?)
        """, (username, role))

        self.connection.commit()

    def remove_admin(self, username):

        username = username.lower()

        self.cursor.execute("""
        DELETE FROM admins
        WHERE username = ?
        """, (username,))

        self.connection.commit()

    def get_admins(self):

        self.cursor.execute("""
        SELECT *
        FROM admins
        ORDER BY role DESC, username
        """)

        return self.cursor.fetchall()

    def admins_count(self):

        self.cursor.execute("""
        SELECT COUNT(*) AS count
        FROM admins
        """)

        return self.cursor.fetchone()["count"]

    def is_admin(self, username):

        username = username.lower()

        self.cursor.execute("""
        SELECT 1
        FROM admins
        WHERE username = ?
        """, (username,))

        return self.cursor.fetchone() is not None

    def is_owner(self, username):

        username = username.lower()

        self.cursor.execute("""
        SELECT 1
        FROM admins
        WHERE username = ?
        AND role='owner'
        """, (username,))

        return self.cursor.fetchone() is not None

    # =====================================================
    # GROUPS
    # =====================================================

    def add_group(self, chat_id, title):

        self.cursor.execute("""
        INSERT OR REPLACE INTO groups_list(chat_id, title)
        VALUES (?, ?)
        """, (chat_id, title))

        self.connection.commit()

    def remove_group(self, chat_id):

        self.cursor.execute("""
        DELETE FROM groups_list
        WHERE chat_id = ?
        """, (chat_id,))

        self.connection.commit()

    def get_groups(self):

        self.cursor.execute("""
        SELECT *
        FROM groups_list
        ORDER BY title
        """)

        return self.cursor.fetchall()

    def group_exists(self, chat_id):

        self.cursor.execute("""
        SELECT 1
        FROM groups_list
        WHERE chat_id = ?
        """, (chat_id,))

        return self.cursor.fetchone() is not None

    # =====================================================
    # ACTIVE GROUP
    # =====================================================

    def set_active_group(self, chat_id):

        self.set_setting("active_group", str(chat_id))

    def get_active_group(self):

        value = self.get_setting("active_group")

        if value is None:
            return None

        return int(value)

    # =====================================================
    # DATABASE
    # =====================================================

    def close(self):

        self.connection.close()