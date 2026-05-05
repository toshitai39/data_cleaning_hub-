"""User management CLI for the Data Profiler.

Usage (from project root):

    python manage_users.py list
    python manage_users.py add <username> <password> "<full name>"
    python manage_users.py passwd <username> <old_password> <new_password>
    python manage_users.py delete <username>

Examples:
    python manage_users.py add toshit "MyPass@123" "Toshit Tejasvat"
    python manage_users.py passwd demo "admin@123" "newpass2026"
    python manage_users.py list
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make sure we can import auth.logic when run from anywhere.
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from auth.logic import (  # noqa: E402
    add_user,
    change_password,
    list_users,
    load_users,
)


USERS_FILE = _ROOT / "auth" / "users.json"


def cmd_list() -> int:
    users = list_users()
    if not users:
        print("No users found.")
        return 0
    print(f"{'USERNAME':<20} {'NAME'}")
    print("-" * 50)
    for u in users:
        print(f"{u['username']:<20} {u.get('name', '')}")
    print(f"\nTotal: {len(users)} user(s)")
    return 0


def cmd_add(username: str, password: str, name: str) -> int:
    if add_user(username, password, name):
        print(f"User '{username}' added successfully.")
        return 0
    print(f"Error: user '{username}' already exists.", file=sys.stderr)
    return 1


def cmd_passwd(username: str, old_password: str, new_password: str) -> int:
    if change_password(username, old_password, new_password):
        print(f"Password for '{username}' changed.")
        return 0
    print(f"Error: invalid username or current password.", file=sys.stderr)
    return 1


def cmd_delete(username: str) -> int:
    data = load_users()
    users = data.get("users", [])
    new_users = [u for u in users if u.get("username") != username]
    if len(new_users) == len(users):
        print(f"Error: user '{username}' not found.", file=sys.stderr)
        return 1
    data["users"] = new_users
    USERS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"User '{username}' deleted.")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0

    cmd = argv[1].lower()

    if cmd == "list":
        return cmd_list()

    if cmd == "add":
        if len(argv) != 5:
            print("Usage: python manage_users.py add <username> <password> \"<full name>\"")
            return 2
        return cmd_add(argv[2], argv[3], argv[4])

    if cmd == "passwd":
        if len(argv) != 5:
            print("Usage: python manage_users.py passwd <username> <old_password> <new_password>")
            return 2
        return cmd_passwd(argv[2], argv[3], argv[4])

    if cmd == "delete":
        if len(argv) != 3:
            print("Usage: python manage_users.py delete <username>")
            return 2
        return cmd_delete(argv[2])

    print(f"Unknown command: {cmd}\n")
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
