"""Smoke tests for the NetSuite connector + credential vault.

These don't hit NetSuite — they exercise the local logic only:

  * NetSuiteCredentials URL / realm derivation.
  * OAuth1 signer builds without raising.
  * credential_vault encrypt → decrypt round-trip.
  * credential_vault graceful fallback when SECRET_KEY is missing.

Run from the repo root with:

    python -m backend.tests.smoke_netsuite

Exits 0 on success, non-zero on the first failed assertion.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

# Make the project root importable when run with `python -m`.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _check(label: str, ok: bool, detail: str = "") -> None:
    """Pretty-print a single assertion outcome and exit on failure."""
    if ok:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  ({detail})")
        sys.exit(1)


def test_url_formatting() -> None:
    """Account ID transforms — production + sandbox."""
    print("URL formatting")
    from backend.app.services.netsuite_connector import NetSuiteCredentials

    prod = NetSuiteCredentials(
        account_id="XX1234567",
        consumer_key="ck", consumer_secret="cs",
        token_id="ti", token_secret="ts",
    )
    _check("prod host lowercased",
           prod.account_for_url == "td3046591",
           prod.account_for_url)
    _check("prod realm uppercased",
           prod.realm == "XX1234567",
           prod.realm)
    _check("prod base URL host",
           prod.base_url == "https://td3046591.suitetalk.api.netsuite.com",
           prod.base_url)
    _check("prod SuiteQL URL path",
           prod.suiteql_url.endswith("/services/rest/query/v1/suiteql"),
           prod.suiteql_url)

    sb = NetSuiteCredentials(
        account_id="XX1234567_SB1",
        consumer_key="ck", consumer_secret="cs",
        token_id="ti", token_secret="ts",
    )
    _check("sandbox host underscore-to-dash",
           sb.account_for_url == "td3046591-sb1",
           sb.account_for_url)
    _check("sandbox realm preserves underscore",
           sb.realm == "XX1234567_SB1",
           sb.realm)

    # Whitespace trim — NetSuite returns INVALID_LOGIN on trailing spaces
    # which is a common copy-paste failure mode.
    trimmed = NetSuiteCredentials(
        account_id="  XX1234567 ",
        consumer_key="  ck ", consumer_secret="cs",
        token_id="ti", token_secret=" ts ",
    )
    _check("post-init whitespace strip",
           trimmed.account_id == "XX1234567" and trimmed.token_secret == "ts",
           f"{trimmed.account_id!r} / {trimmed.token_secret!r}")


def test_oauth_signer_builds() -> None:
    """OAuth1 signer instantiates without raising."""
    print("OAuth1 signer")
    from backend.app.services.netsuite_connector import (
        NetSuiteCredentials, _build_oauth,
    )

    creds = NetSuiteCredentials(
        account_id="XX1234567",
        consumer_key="ck", consumer_secret="cs",
        token_id="ti", token_secret="ts",
    )
    signer = _build_oauth(creds)
    _check("signer instantiated", signer is not None)


def test_vault_roundtrip_with_secret() -> None:
    """Encrypt → store on a fake Project → decrypt back."""
    print("Credential vault (Fernet path)")
    os.environ["SECRET_KEY"] = "smoke-test-secret-do-not-use-in-prod"
    # Force re-init in case an earlier import cached _CIPHER without a key.
    from backend.app.services import credential_vault as cv
    cv._CIPHER = None
    cv._FAILED_INIT = False

    project = SimpleNamespace(extra={})
    payload = {
        "account_id": "XX1234567",
        "consumer_key": "ck",
        "consumer_secret": "cs",
        "token_id": "ti",
        "token_secret": "ts",
    }
    cv.save_credentials(project, "netsuite", payload)

    # On disk, the consumer_secret must NOT appear verbatim.
    serialized = repr(project.extra)
    _check("no plaintext secret in envelope",
           "cs" not in serialized.split("_connectors")[1] if "_connectors" in serialized else False,
           "plaintext leaked into project.extra")

    loaded = cv.load_credentials(project, "netsuite")
    _check("roundtrip recovers payload", loaded == payload, str(loaded))

    removed = cv.delete_credentials(project, "netsuite")
    _check("delete reports removed", removed is True)
    _check("delete clears blob",
           cv.load_credentials(project, "netsuite") is None,
           "still present after delete")


def test_vault_plaintext_fallback() -> None:
    """When SECRET_KEY is missing, vault should still save+load (plaintext)."""
    print("Credential vault (no SECRET_KEY -> plaintext fallback)")
    os.environ.pop("SECRET_KEY", None)
    os.environ.pop("FERNET_SECRET", None)
    from backend.app.services import credential_vault as cv
    cv._CIPHER = None
    cv._FAILED_INIT = False

    project = SimpleNamespace(extra={})
    payload = {"account_id": "X", "consumer_key": "k"}
    cv.save_credentials(project, "netsuite", payload)
    loaded = cv.load_credentials(project, "netsuite")
    _check("plaintext fallback roundtrip", loaded == payload, str(loaded))
    # And the envelope should advertise version 0 so the next deploy with
    # SECRET_KEY set knows it's looking at plaintext.
    env = project.extra["_connectors"]["netsuite"]
    _check("plaintext envelope version=0", env.get("v") == 0, str(env))


def test_query_lookup() -> None:
    """All stream tables in the catalog have a canned SuiteQL query."""
    print("Stream query coverage")
    from backend.app.catalog import STREAM_SCHEMAS
    from backend.app.services.netsuite_connector import query_for_table

    missing = []
    for (system_id, stream_id), tables in STREAM_SCHEMAS.items():
        if system_id != "netsuite":
            continue
        for t in tables:
            if query_for_table(stream_id, t["id"]) is None:
                missing.append(f"{stream_id}.{t['id']}")
    _check("every netsuite catalog table has a query",
           not missing,
           "missing: " + ", ".join(missing))


def main() -> None:
    print("=" * 60)
    print("NetSuite smoke tests")
    print("=" * 60)
    test_url_formatting()
    test_oauth_signer_builds()
    test_vault_roundtrip_with_secret()
    test_vault_plaintext_fallback()
    test_query_lookup()
    print("-" * 60)
    print("All NetSuite smoke tests passed.")


if __name__ == "__main__":
    main()
