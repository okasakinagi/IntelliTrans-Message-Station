from flask_login import UserMixin


class User(UserMixin):
    """Lightweight in-memory user model backed by the session.

    For a production system this would be backed by a proper data store;
    here we keep things simple so the focus stays on the messaging layer.
    """

    def __init__(self, username: str):
        self.username = username

    # Flask-Login requires get_id() to return a string identifier.
    def get_id(self) -> str:
        return self.username

    @staticmethod
    def get(user_id: str) -> "User | None":
        """Reconstruct a User from the session user_id."""
        if user_id:
            return User(user_id)
        return None
