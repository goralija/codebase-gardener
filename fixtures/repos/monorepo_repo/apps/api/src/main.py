from .db.users import USERS


def get_user(username: str) -> dict[str, str] | None:
    return USERS.get(username)
