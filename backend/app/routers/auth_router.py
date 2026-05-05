"""Authentication endpoints — wraps existing auth/logic.py."""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from auth.logic import add_user, authenticate

from ..schemas import LoginRequest, LoginResponse
from ..session_store import store

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------- /login --------------------------------------------------------

@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    user = authenticate(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    sid = str(uuid.uuid4())
    sess = store.get(sid)
    sess.user = {"username": user["username"], "name": user.get("name", user["username"])}
    return LoginResponse(
        session_id=sid,
        username=user["username"],
        name=user.get("name", user["username"]),
    )


@router.post("/logout")
def logout(session_id: str) -> dict:
    store.reset(session_id)
    return {"ok": True}


# ---------- /register -----------------------------------------------------

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=6, max_length=128)


class RegisterResponse(BaseModel):
    session_id: str
    username: str
    name: str


@router.post("/register", response_model=RegisterResponse)
def register(body: RegisterRequest) -> RegisterResponse:
    """Sign up a new user and immediately log them in.

    Stores a SHA-256 hashed password in auth/users.json (via auth.logic.add_user).
    """
    username = body.username.strip()
    name = body.name.strip()

    # Username sanity: alphanumeric + dot/underscore/hyphen only.
    if not re.fullmatch(r"[A-Za-z0-9._-]+", username):
        raise HTTPException(
            status_code=400,
            detail="Username may only contain letters, digits, dot, underscore, hyphen.",
        )
    if not name:
        raise HTTPException(status_code=400, detail="Display name is required.")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    if not add_user(username, body.password, name):
        raise HTTPException(status_code=409, detail="Username already exists.")

    # Auto-login after successful registration.
    sid = str(uuid.uuid4())
    sess = store.get(sid)
    sess.user = {"username": username, "name": name}
    return RegisterResponse(session_id=sid, username=username, name=name)
