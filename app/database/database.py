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

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaigns(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            chat_ids TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """)

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaign_blocks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            seq_order INTEGER NOT NULL,
            block_start TEXT NOT NULL,
            block_end TEXT NOT NULL,
            message_text TEXT NOT NULL,
            send_count INTEGER,
            interval_seconds INTEGER,
            FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
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
    # CAMPAIGNS
    # =====================================================

    def create_campaign(self, name, start_time, end_time, chat_ids, blocks):
        import json
        from datetime import datetime
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        chat_ids_json = json.dumps(chat_ids)

        self.cursor.execute("""
        INSERT INTO campaigns(name, start_time, end_time, chat_ids, enabled, created_at)
        VALUES (?, ?, ?, ?, 1, ?)
        """, (name, start_time, end_time, chat_ids_json, now_str))
        campaign_id = self.cursor.lastrowid

        for seq, block in enumerate(blocks, 1):
            self.cursor.execute("""
            INSERT INTO campaign_blocks(campaign_id, seq_order, block_start, block_end, message_text, send_count, interval_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                campaign_id,
                seq,
                block["block_start"],
                block["block_end"],
                block["message_text"],
                block.get("send_count"),
                block.get("interval_seconds"),
            ))

        self.connection.commit()
        return campaign_id

    def get_campaigns(self):
        import json
        self.cursor.execute("""
        SELECT * FROM campaigns ORDER BY id DESC
        """)
        rows = self.cursor.fetchall()
        result = []
        for row in rows:
            camp = dict(row)
            camp["chat_ids"] = json.loads(camp["chat_ids"])
            camp["blocks"] = self.get_campaign_blocks(camp["id"])
            result.append(camp)
        return result

    def get_campaign(self, campaign_id):
        import json
        self.cursor.execute("""
        SELECT * FROM campaigns WHERE id = ?
        """, (campaign_id,))
        row = self.cursor.fetchone()
        if not row:
            return None
        camp = dict(row)
        camp["chat_ids"] = json.loads(camp["chat_ids"])
        camp["blocks"] = self.get_campaign_blocks(campaign_id)
        return camp

    def get_campaign_blocks(self, campaign_id):
        self.cursor.execute("""
        SELECT * FROM campaign_blocks WHERE campaign_id = ? ORDER BY seq_order ASC
        """, (campaign_id,))
        return [dict(row) for row in self.cursor.fetchall()]

    def delete_campaign(self, campaign_id):
        self.cursor.execute("DELETE FROM campaign_blocks WHERE campaign_id = ?", (campaign_id,))
        self.cursor.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
        self.connection.commit()

    def toggle_campaign(self, campaign_id, enabled):
        self.cursor.execute("UPDATE campaigns SET enabled = ? WHERE id = ?", (1 if enabled else 0, campaign_id))
        self.connection.commit()

    # =====================================================
    # DATABASE
    # =====================================================

    def close(self):

        self.connection.close()