"""Per-project encrypted credential storage.

Connector credentials (NetSuite TBA tokens, future Oracle / Workday
keys, etc.) need to survive a server restart so the steward isn't
re-typing five fields every session. But storing OAuth secrets in
plaintext alongside project metadata is unacceptable.

This module wraps the existing ``Project.extra`` JSON column with a
Fernet symmetric-encryption layer keyed off the application's
``SECRET_KEY`` (already used for JWT signing). The plaintext lives
only in process memory; on disk every credential field is an
opaque base64 blob.

API:
    save_credentials(project, system, payload)  → encrypts into project.extra
    load_credentials(project, system)           → decrypts back to dict
    delete_credentials(project, system)         → removes the blob

If ``SECRET_KEY`` is missing or the cryptography package fails to
import, the vault degrades gracefully: it falls back to plaintext
storage with a one-line log warning. That preserves usability on
local dev while keeping production safe.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


_CIPHER = None
_FAILED_INIT = False


def _cipher():
    """Lazy-init a Fernet cipher derived from ``SECRET_KEY``.

    Fernet wants a 32-byte url-safe-base64 key. We hash the secret
    with SHA-256 (always 32 bytes) and base64-encode it — deterministic,
    so the key is stable across restarts as long as SECRET_KEY is.
    """
    global _CIPHER, _FAILED_INIT
    if _CIPHER is not None or _FAILED_INIT:
        return _CIPHER
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.warning(
            "cryptography not installed — connector credentials will be "
            "stored as PLAINTEXT in project.extra. Add `cryptography` to "
            "requirements.txt and redeploy to enable encryption at rest."
        )
        _FAILED_INIT = True
        return None
    secret = os.environ.get("SECRET_KEY") or os.environ.get("FERNET_SECRET") or ""
    if not secret:
        logger.warning(
            "SECRET_KEY missing — connector credentials will be stored as "
            "PLAINTEXT in project.extra. Set SECRET_KEY in the environment "
            "(Render Blueprint already does this via generateValue: true)."
        )
        _FAILED_INIT = True
        return None
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    _CIPHER = Fernet(key)
    return _CIPHER


def _encrypt(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return an encrypted envelope ``{"v": 1, "enc": "<token>"}``.

    The version byte gives us a clean upgrade path if we ever rotate
    the encryption scheme (Fernet → AES-GCM, key derivation change,
    etc.). The decryptor reads ``v`` first and dispatches accordingly.
    """
    cipher = _cipher()
    plaintext = json.dumps(payload).encode("utf-8")
    if cipher is None:
        # Plaintext fallback — flag the envelope so we know not to
        # try and decrypt on the way out.
        return {"v": 0, "plain": payload}
    token = cipher.encrypt(plaintext)
    return {"v": 1, "enc": token.decode("ascii")}


def _decrypt(envelope: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Reverse of ``_encrypt``. Returns ``None`` if decryption fails
    (the envelope is corrupt, the SECRET_KEY rotated without
    re-encryption, etc.) — caller should treat that as "no creds
    saved" rather than crashing the request."""
    if not isinstance(envelope, dict):
        return None
    version = envelope.get("v")
    if version == 0:
        plain = envelope.get("plain")
        return plain if isinstance(plain, dict) else None
    if version == 1:
        cipher = _cipher()
        if cipher is None:
            return None
        try:
            token = envelope["enc"].encode("ascii")
            plaintext = cipher.decrypt(token)
            return json.loads(plaintext.decode("utf-8"))
        except Exception as exc:
            logger.warning("Credential decrypt failed for v1 envelope: %s", exc)
            return None
    return None


# ── Project.extra storage helpers ─────────────────────────────────────────

_CONNECTOR_KEY = "_connectors"


def save_credentials(project, system: str, payload: Dict[str, Any]) -> None:
    """Encrypt + persist credentials for ``system`` on ``project.extra``.

    ``project.extra`` is a JSON column already used by other features;
    we namespace under ``_connectors[<system>]`` so this doesn't collide
    with anything else stored there.
    """
    extra = dict(project.extra or {})
    connectors = dict(extra.get(_CONNECTOR_KEY) or {})
    connectors[system] = _encrypt(payload)
    extra[_CONNECTOR_KEY] = connectors
    project.extra = extra


def load_credentials(project, system: str) -> Optional[Dict[str, Any]]:
    """Return the decrypted credential dict for ``system`` on
    ``project``, or ``None`` if nothing is saved or decryption fails."""
    if project is None or not project.extra:
        return None
    connectors = (project.extra or {}).get(_CONNECTOR_KEY) or {}
    envelope = connectors.get(system)
    if not envelope:
        return None
    return _decrypt(envelope)


def delete_credentials(project, system: str) -> bool:
    """Remove the stored envelope for ``system``. Returns True if
    something was removed."""
    if project is None or not project.extra:
        return False
    extra = dict(project.extra)
    connectors = dict(extra.get(_CONNECTOR_KEY) or {})
    if system in connectors:
        connectors.pop(system, None)
        extra[_CONNECTOR_KEY] = connectors
        project.extra = extra
        return True
    return False
