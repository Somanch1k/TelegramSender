class AdminService:

    def __init__(self, database):
        self.db = database

    def setup_owner(self, username):
        """Ensures that the account used by this local client is an owner."""
        if not self.db.is_owner(username):
            self.db.add_admin(username, "owner")
            return True
        return False

    def has_access(self, username):
        return self.is_owner(username) or self.is_admin(username)

    def is_owner(self, username):
        return self.db.is_owner(username)

    def is_admin(self, username):
        return self.db.is_admin(username)

    def add_admin(self, username):
        username = username.replace("@", "")
        self.db.add_admin(username, "admin")

    def remove_admin(self, username):
        username = username.replace("@", "")
        self.db.remove_admin(username)

    def get_admins(self):
        return self.db.get_admins()
