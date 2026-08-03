import json


class GroupService:

    def __init__(self, database):
        self.db = database

    def add_group(self, chat_id, title):
        self.db.cursor.execute("""
        INSERT OR REPLACE INTO groups_list(chat_id, title)
        VALUES (?, ?)
        """, (chat_id, title))

        self.db.connection.commit()

    def remove_group(self, chat_id):
        self.db.cursor.execute("""
        DELETE FROM groups_list
        WHERE chat_id = ?
        """, (chat_id,))

        self.db.connection.commit()

    def get_groups(self):
        self.db.cursor.execute("""
        SELECT *
        FROM groups_list
        ORDER BY title
        """)

        return self.db.cursor.fetchall()

    def is_group_exists(self, chat_id):
        self.db.cursor.execute("""
        SELECT *
        FROM groups_list
        WHERE chat_id = ?
        """, (chat_id,))

        return self.db.cursor.fetchone() is not None

    def set_active_group(self, chat_id):
        self.db.set_active_group(chat_id)

    def get_active_group(self):
        return self.db.get_active_group()

    def set_selected_groups(self, dialogs):
        """Stores the current recipients and remembers their titles."""
        group_ids = []
        for dialog in dialogs:
            self.add_group(dialog.id, dialog.name)
            group_ids.append(dialog.id)
        self.db.set_setting("selected_group_ids", json.dumps(group_ids))

    def get_selected_groups(self):
        raw_ids = self.db.get_setting("selected_group_ids")
        if not raw_ids:
            # Compatibility with the earlier single-group selection.
            active_group = self.get_active_group()
            return [active_group] if active_group is not None else []
        try:
            return [int(chat_id) for chat_id in json.loads(raw_ids)]
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    def set_interval(self, seconds):
        self.db.set_setting("send_interval", str(seconds))

    def get_interval(self):
        value = self.db.get_setting("send_interval")
        return int(value) if value is not None else 10
