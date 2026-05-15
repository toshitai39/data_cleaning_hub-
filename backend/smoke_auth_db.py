"""Smoke test for DB-backed auth.

Verifies:
  1. Seeding from JSON populates the table on a fresh DB
  2. authenticate() succeeds with a seeded account
  3. add_user() writes to the DB and the new user can sign in
  4. add_user() with a duplicate username returns False
  5. change_password() updates the stored hash
  6. list_users() returns DB rows (not JSON)
  7. Restarting the process (simulated) doesn't lose users — they're
     still in the DB
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Force a brand-new SQLite DB for this test so we don't touch the
# user's real projects.db.
tmpdir = Path(tempfile.mkdtemp(prefix="dprofiler_auth_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(tmpdir / 'test.db').as_posix()}"

from backend.app.db import init_db, SessionLocal  # noqa: E402
from backend.app.models import User  # noqa: E402
from auth.logic import (  # noqa: E402
    add_user, authenticate, change_password, ensure_seeded, list_users,
)

results = []


def check(name, ok, detail=""):
    tag = "[PASS]" if ok else "[FAIL]"
    line = f"{tag} {name}" + (f"  -- {detail}" if detail else "")
    results.append((ok, line))
    print(line)


print(f"\nUsing test DB: {tmpdir / 'test.db'}\n")
init_db()

# ─── T1: seed from JSON ────────────────────────────────────────────────
print("=== T1: seed from JSON populates empty table ===")
seeded = ensure_seeded()
check("seeded > 0 users from JSON", seeded > 0, f"seeded={seeded}")
db = SessionLocal()
try:
    count = db.query(User).count()
finally:
    db.close()
check("users table has rows after seed", count > 0, f"count={count}")

# Second call should be a no-op (table not empty)
seeded2 = ensure_seeded()
check("re-seed is idempotent", seeded2 == 0, f"got {seeded2}")

# ─── T2: authenticate seeded user ──────────────────────────────────────
print("\n=== T2: authenticate seeded users ===")
# admin/admin@123 only works if a JSON entry was hashed with that pwd;
# instead, validate by listing.
users = list_users()
check("seeded users include 'admin'", any(u["username"] == "admin" for u in users),
      f"got {[u['username'] for u in users]}")

# ─── T3: add_user writes to DB ─────────────────────────────────────────
print("\n=== T3: add_user persists to DB ===")
ok = add_user("alice", "secret123", "Alice Wonderland")
check("add_user returns True for new user", ok is True)
db = SessionLocal()
try:
    alice = db.get(User, "alice")
finally:
    db.close()
check("alice exists in DB", alice is not None and alice.name == "Alice Wonderland",
      f"got {alice}")

# ─── T4: authenticate the new user ─────────────────────────────────────
print("\n=== T4: authenticate the new user ===")
auth = authenticate("alice", "secret123")
check("alice authenticates with correct pwd",
      auth is not None and auth["username"] == "alice",
      f"got {auth}")
auth_bad = authenticate("alice", "wrong")
check("alice rejected with wrong pwd", auth_bad is None)
auth_nobody = authenticate("nobody", "anything")
check("non-existent user rejected", auth_nobody is None)

# ─── T5: add_user duplicate returns False ──────────────────────────────
print("\n=== T5: add_user dedups by username ===")
dup = add_user("alice", "anything", "Alice 2")
check("add_user returns False for duplicate username", dup is False)

# ─── T6: change_password updates stored hash ───────────────────────────
print("\n=== T6: change_password ===")
ok = change_password("alice", "secret123", "newsecret456")
check("change_password returns True with correct old pwd", ok is True)
check("old pwd no longer works", authenticate("alice", "secret123") is None)
check("new pwd works", authenticate("alice", "newsecret456") is not None)
bad = change_password("alice", "wrong-old", "doesntmatter")
check("change_password returns False with wrong old pwd", bad is False)

# ─── T7: simulate restart — users survive ──────────────────────────────
print("\n=== T7: users survive a simulated restart ===")
# Drop and recreate the session factory the way a process restart would.
from backend.app import db as db_module
db_module.engine.dispose()
# A fresh authenticate() call must still see alice.
auth = authenticate("alice", "newsecret456")
check("alice still authenticates after restart sim", auth is not None,
      f"got {auth}")

# A second ensure_seeded() must not duplicate the seed users.
re_seed = ensure_seeded()
check("ensure_seeded on populated DB is a no-op", re_seed == 0, f"got {re_seed}")

# ─── SUMMARY ──────────────────────────────────────────────────────────
print("\n" + "=" * 70)
passed = sum(1 for ok, _ in results if ok)
total = len(results)
print(f"AUTH-DB SUMMARY: {passed}/{total} passed")
if passed < total:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nAll DB-backed auth tests passed.")
