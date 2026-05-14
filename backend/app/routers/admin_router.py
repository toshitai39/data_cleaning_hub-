"""Admin endpoints — small surface for operational visibility.

The whole router is gated on the ``ADMIN_TOKEN`` environment variable:
  • If the variable is unset, every endpoint returns 503 (so the router
    is effectively disabled locally / wherever the secret isn't provided).
  • If set, the caller must present the same value either as the
    ``X-Admin-Token`` header or the ``?token=`` query string.

Set the secret on Render:
  Service → Environment → Add ``ADMIN_TOKEN`` → some long random string.
Then hit (replace <token>):
  https://<your-render-url>/admin/user-count?token=<token>
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from auth.logic import list_users

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(header_token: Optional[str], query_token: Optional[str]) -> None:
    expected = os.environ.get("ADMIN_TOKEN")
    if not expected:
        # Endpoint disabled — no secret configured on this deployment.
        raise HTTPException(status_code=503, detail="Admin endpoints disabled.")
    presented = header_token or query_token
    if not presented or presented != expected:
        raise HTTPException(status_code=401, detail="Invalid admin token.")


@router.get("/user-count")
def user_count(
    x_admin_token: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
) -> dict:
    """Return the registered-user count plus their usernames + display names.

    Source of truth is ``auth/users.json`` (which is what every other
    auth code path reads from too). Doesn't include passwords or session
    activity — strictly "how many people have signed up?".
    """
    _require_admin(x_admin_token, token)
    users = list_users()
    return {
        "count": len(users),
        "users": users,
    }
