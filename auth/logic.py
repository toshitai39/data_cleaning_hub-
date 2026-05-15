"""Authentication logic — DB-backed with JSON seed fallback.

Why DB-backed: Render (and most container hosts) use an ephemeral file
system. Any user written to ``auth/users.json`` at runtime is wiped on
the next deploy, restart, or scale event. That's exactly the bug the
team was hitting — new sign-ups disappearing after a few hours. The DB
is the only persistence layer that survives a redeploy.

``auth/users.json`` now plays a different role:

  • Bootstrap: on first startup (empty ``users`` table), every entry
    from the JSON is inserted into the DB. This preserves the existing
    accounts (admin, krishna, etc.) without manual migration.
  • Reference only: changes to the JSON do NOT affect the running
    system once the DB has been seeded. Edit the JSON only to set the
    initial admin password on a brand-new deployment.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import SessionLocal
from backend.app.models import User

logger = logging.getLogger(__name__)

USERS_FILE = Path(__file__).parent / "users.json"


def _hash_password(password: str) -> str:
    """SHA-256 with a fixed salt prefix. Mirrors the legacy hash so
    accounts seeded from the JSON file still authenticate without a
    forced password reset."""
    salted = f"dprofiler_salt$${password}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()


def _is_hashed(password_value: str) -> bool:
    return len(password_value) == 64 and all(c in "0123456789abcdef" for c in password_value)


def _seed_from_json_if_empty(db: Session) -> int:
    """First-run bootstrap: if the users table is empty, insert every
    user defined in ``auth/users.json`` so existing accounts keep
    working after the JSON→DB migration. Returns the number of users
    seeded (0 if the table was already populated or the file is gone)."""
    if db.scalar(select(User).limit(1)) is not None:
        return 0
    if not USERS_FILE.exists():
        # No JSON either — write the default admin so the deployment is
        # at least usable.
        db.add(User(
            username="admin",
            name="Administrator",
            password=_hash_password("admin@123"),
        ))
        db.commit()
        logger.info("auth: seeded default admin user (no users.json found).")
        return 1
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning("auth: could not read users.json (%s); skipping seed.", exc)
        return 0
    seeded = 0
    for entry in data.get("users", []):
        username = (entry.get("username") or "").strip()
        if not username:
            continue
        stored = entry.get("password", "")
        # Migrate plaintext on the way in so we never store cleartext.
        password = stored if _is_hashed(stored) else _hash_password(stored)
        db.add(User(
            username=username,
            name=entry.get("name") or username,
            password=password,
        ))
        seeded += 1
    if seeded:
        db.commit()
        logger.info("auth: seeded %d users from users.json into the DB.", seeded)
    return seeded


def ensure_seeded() -> int:
    """Public entry point — called once at app startup so the DB has
    accounts to authenticate against. Safe to call repeatedly."""
    db = SessionLocal()
    try:
        return _seed_from_json_if_empty(db)
    finally:
        db.close()


def authenticate(username: str, password: str) -> Optional[Dict]:
    """Validate credentials against the DB."""
    db = SessionLocal()
    try:
        user = db.get(User, username)
        if user is None:
            return None
        if user.password != _hash_password(password):
            return None
        return {"username": user.username, "name": user.name}
    finally:
        db.close()


def list_users() -> List[Dict]:
    """Return all users (no passwords) ordered by username."""
    db = SessionLocal()
    try:
        rows = db.scalars(select(User).order_by(User.username)).all()
        return [{"username": u.username, "name": u.name} for u in rows]
    finally:
        db.close()


def add_user(username: str, password: str, name: str) -> bool:
    """Insert a new user. Returns False if the username is taken.

    Writes to the DB only — Render's filesystem is ephemeral so writing
    to ``users.json`` here would silently undo itself on the next
    redeploy. The JSON file is intentionally not touched anymore.
    """
    db = SessionLocal()
    try:
        if db.get(User, username) is not None:
            return False
        db.add(User(
            username=username,
            name=name,
            password=_hash_password(password),
        ))
        db.commit()
        return True
    finally:
        db.close()


def change_password(username: str, old_password: str, new_password: str) -> bool:
    """Change a user's password after verifying the old one."""
    db = SessionLocal()
    try:
        user = db.get(User, username)
        if user is None or user.password != _hash_password(old_password):
            return False
        user.password = _hash_password(new_password)
        db.commit()
        return True
    finally:
        db.close()
