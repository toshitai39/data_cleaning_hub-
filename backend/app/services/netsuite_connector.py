"""NetSuite SuiteQL connector — OAuth 1.0a Token-Based Authentication.

NetSuite's REST APIs use OAuth 1.0a (TBA), NOT OAuth 2.0. That means
every request needs an ``Authorization`` header constructed from:

  • consumer_key / consumer_secret   (the integration record)
  • token_id / token_secret           (the user's access token)
  • realm                             (the account ID, uppercased)
  • signature_method=HMAC-SHA256, signature_version=1.0
  • timestamp + nonce                 (per-request, must be unique)

The signature is computed over the HTTP method, the full URL, and a
sorted list of the OAuth params — same algorithm Twitter / Flickr
made famous a decade ago. We use ``oauthlib`` so we don't reinvent
that crypto.

SuiteQL is NetSuite's read-only SQL dialect over the SuiteAnalytics
data model. The endpoint is:

    POST https://{account-with-dashes}.suitetalk.api.netsuite.com
         /services/rest/query/v1/suiteql

Body: {"q": "SELECT ... FROM ..."}

Account ID transform: ``XX1234567`` (URL: ``td3046591``);
``XX1234567_SB1`` (URL: ``td3046591-sb1``). Lowercase + underscores
become dashes.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from requests_oauthlib import OAuth1

logger = logging.getLogger(__name__)


@dataclass
class NetSuiteCredentials:
    """Five fields needed to hit a NetSuite REST endpoint with TBA."""
    account_id: str
    consumer_key: str
    consumer_secret: str
    token_id: str
    token_secret: str

    def __post_init__(self) -> None:
        # Trim whitespace from every field — copy-paste errors are common
        # and NetSuite returns "INVALID_LOGIN" with no detail when one
        # cred has a trailing space.
        for f in ("account_id", "consumer_key", "consumer_secret", "token_id", "token_secret"):
            v = getattr(self, f)
            if not isinstance(v, str):
                continue
            object.__setattr__(self, f, v.strip())

    @property
    def account_for_url(self) -> str:
        """Format the Account ID for the URL host: lowercase, underscores
        replaced with dashes. ``XX1234567`` → ``td3046591``;
        ``XX1234567_SB1`` (sandbox) → ``td3046591-sb1``."""
        return self.account_id.strip().replace("_", "-").lower()

    @property
    def realm(self) -> str:
        """The ``realm`` OAuth parameter — NetSuite requires the Account
        ID in its ORIGINAL case here (not the URL-formatted form)."""
        return self.account_id.strip().upper().replace("-", "_")

    @property
    def base_url(self) -> str:
        return f"https://{self.account_for_url}.suitetalk.api.netsuite.com"

    @property
    def suiteql_url(self) -> str:
        return f"{self.base_url}/services/rest/query/v1/suiteql"


def _build_oauth(creds: NetSuiteCredentials) -> OAuth1:
    """Build the OAuth1 signer NetSuite expects.

    Note: signature_type='auth_header' is the only mode NetSuite
    accepts — passing OAuth params in the URL query or POST body
    yields ``INVALID_LOGIN_ATTEMPT``.
    """
    return OAuth1(
        client_key=creds.consumer_key,
        client_secret=creds.consumer_secret,
        resource_owner_key=creds.token_id,
        resource_owner_secret=creds.token_secret,
        realm=creds.realm,
        signature_method="HMAC-SHA256",
        signature_type="auth_header",
        nonce=str(uuid.uuid4().hex),
        timestamp=str(int(time.time())),
    )


def test_connection(creds: NetSuiteCredentials) -> Dict[str, Any]:
    """Hit a trivial SuiteQL query to verify the credentials work.

    Returns ``{"ok": True, "account_label": "...", "rows_returned": int}``
    on success. On failure returns ``{"ok": False, "error": "<msg>",
    "status_code": int}`` with the most useful diagnostic information
    we can extract from NetSuite's response (their error messages are
    cryptic but the HTTP status is always meaningful).
    """
    # Cheapest possible query — DUAL is a one-row, one-column virtual
    # table that always responds successfully if the auth is valid.
    try:
        resp = requests.post(
            creds.suiteql_url,
            json={"q": "SELECT 1 AS heartbeat FROM DUAL"},
            auth=_build_oauth(creds),
            headers={"Prefer": "transient", "Content-Type": "application/json"},
            timeout=15,
        )
    except requests.RequestException as exc:
        return {"ok": False, "error": f"Network error: {exc}", "status_code": 0}

    if resp.status_code == 200:
        payload = resp.json() if resp.content else {}
        return {
            "ok": True,
            "account_label": creds.account_id,
            "base_url": creds.base_url,
            "rows_returned": int(payload.get("count", 1)),
        }

    # Pull the most useful error nugget. NetSuite returns a JSON-API
    # style error envelope: ``{"o:errorDetails": [{"detail": "..."}]}``.
    error_msg = f"HTTP {resp.status_code}"
    try:
        body = resp.json()
        details = body.get("o:errorDetails") or []
        if details:
            error_msg = details[0].get("detail") or details[0].get("o:errorCode") or error_msg
        elif "title" in body:
            error_msg = body["title"]
    except Exception:
        if resp.text:
            error_msg += f": {resp.text[:200]}"
    return {"ok": False, "error": error_msg, "status_code": resp.status_code}


def run_suiteql(
    creds: NetSuiteCredentials,
    query: str,
    limit: int = 1000,
    offset: int = 0,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Execute one SuiteQL query and return ``(df, meta)``.

    The SuiteQL endpoint paginates internally; for a first cut we run
    a single page of up to ``limit`` rows (max 1000 per NetSuite's
    documented cap). Pagination is wired in but we only follow it
    when the caller explicitly asks for more by raising ``limit``.

    ``meta`` carries the raw NetSuite response envelope (``count``,
    ``hasMore``, ``links``) so the UI can show "showing 1000 of N"
    semantics without re-fetching.
    """
    rows: List[Dict[str, Any]] = []
    total_fetched = 0
    has_more = True
    cur_offset = offset
    last_meta: Dict[str, Any] = {}

    while has_more and total_fetched < limit:
        page_limit = min(1000, limit - total_fetched)
        url = f"{creds.suiteql_url}?limit={page_limit}&offset={cur_offset}"
        try:
            resp = requests.post(
                url,
                json={"q": query},
                auth=_build_oauth(creds),
                headers={"Prefer": "transient", "Content-Type": "application/json"},
                timeout=60,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"NetSuite network error: {exc}") from exc

        if resp.status_code != 200:
            # Surface NetSuite's most specific error message.
            err = f"NetSuite returned HTTP {resp.status_code}"
            try:
                body = resp.json()
                details = body.get("o:errorDetails") or []
                if details:
                    err = details[0].get("detail") or err
                elif "title" in body:
                    err = body["title"]
            except Exception:
                pass
            raise RuntimeError(err)

        payload = resp.json()
        page_rows = payload.get("items", [])
        rows.extend(page_rows)
        total_fetched += len(page_rows)
        has_more = bool(payload.get("hasMore", False))
        cur_offset += len(page_rows)
        last_meta = {
            "count": payload.get("count", len(page_rows)),
            "hasMore": has_more,
            "totalResults": payload.get("totalResults"),
        }
        if not page_rows:
            break

    df = pd.DataFrame(rows)
    # NetSuite buries a ``links`` array in each row — useless noise
    # for analytics and a JSON-serialisation footgun later.
    if "links" in df.columns:
        df = df.drop(columns=["links"])
    return df, last_meta


# ── Per-stream query templates ────────────────────────────────────────────
#
# Each (system_id, stream_id, table_id) entry maps to a SuiteQL query.
# The connector router looks up the query by (stream_id, table_id), runs
# it, and lands the result as a DataFrame. Keep the SELECT list narrow
# enough that NetSuite doesn't time out on wide tables — we only fetch
# the columns the profiler / cleansing engine actually needs.

_STREAM_QUERIES: Dict[Tuple[str, str], str] = {
    # ── Customer ───────────────────────────────────────────────
    ("customer", "customer"): (
        "SELECT id, entityid, companyname, email, phone, "
        "       isinactive, datecreated, lastmodifieddate, "
        "       currency, terms, salesrep, subsidiary, category "
        "FROM customer"
    ),
    ("customer", "customeraddressbook"): (
        "SELECT entity, addressbookaddress AS addrkey, defaultbilling, defaultshipping "
        "FROM customeraddressbook"
    ),
    ("customer", "customercategory"): (
        "SELECT id, name, isinactive FROM customercategory"
    ),
    ("customer", "subsidiary"): (
        "SELECT id, name, country, currency, isinactive, fiscalcalendar "
        "FROM subsidiary"
    ),

    # ── Vendor ─────────────────────────────────────────────────
    ("vendor", "vendor"): (
        "SELECT id, entityid, companyname, email, phone, "
        "       isinactive, datecreated, lastmodifieddate, "
        "       currency, terms, category, subsidiary "
        "FROM vendor"
    ),
    ("vendor", "vendoraddressbook"): (
        "SELECT entity, addressbookaddress AS addrkey, defaultbilling, defaultshipping "
        "FROM vendoraddressbook"
    ),
    ("vendor", "vendorcategory"): (
        "SELECT id, name, isinactive FROM vendorcategory"
    ),

    # ── Material / Item ────────────────────────────────────────
    ("material", "item"): (
        "SELECT id, itemid, displayname, itemtype, isinactive, "
        "       baseprice, cost, weightunit, weight, "
        "       lastmodifieddate, createddate "
        "FROM item"
    ),
    ("material", "inventoryitem"): (
        "SELECT id, averagecost, lastpurchaseprice, "
        "       quantityonhand, quantityavailable, reorderpoint "
        "FROM inventoryitem"
    ),

    # ── Employee ───────────────────────────────────────────────
    ("employee", "employee"): (
        "SELECT id, entityid, firstname, lastname, email, title, "
        "       hiredate, releasedate, isinactive, subsidiary, department "
        "FROM employee"
    ),

    # ── GL Account ─────────────────────────────────────────────
    ("gl_account", "account"): (
        "SELECT id, acctnumber, accountsearchdisplayname, accttype, "
        "       currency, isinactive, subsidiary "
        "FROM account"
    ),
}


def get_global_credentials() -> Optional[NetSuiteCredentials]:
    """Read NetSuite credentials from environment variables.

    When NETSUITE_ACCOUNT_ID (+ the four token fields) are set, the
    credential form on the Load data page is hidden entirely — users
    connect with one click and never need to enter or manage secrets
    themselves. Intended for client deployments where an admin
    configures the integration once in .env / Render dashboard.

    Returns None when any of the five required vars is absent.
    """
    import os
    account_id = os.environ.get("NETSUITE_ACCOUNT_ID", "").strip()
    if not account_id:
        return None
    consumer_key    = os.environ.get("NETSUITE_CONSUMER_KEY", "").strip()
    consumer_secret = os.environ.get("NETSUITE_CONSUMER_SECRET", "").strip()
    token_id        = os.environ.get("NETSUITE_TOKEN_ID", "").strip()
    token_secret    = os.environ.get("NETSUITE_TOKEN_SECRET", "").strip()
    if not all([consumer_key, consumer_secret, token_id, token_secret]):
        return None
    return NetSuiteCredentials(
        account_id=account_id,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        token_id=token_id,
        token_secret=token_secret,
    )


def query_for_table(stream_id: str, table_id: str) -> Optional[str]:
    """Look up the canned SuiteQL for one (stream, table) pair."""
    return _STREAM_QUERIES.get((stream_id, table_id))


def list_supported_streams() -> List[str]:
    """Streams with at least one canned query — used by the UI to enable
    or grey out stream tiles."""
    return sorted({stream for stream, _ in _STREAM_QUERIES.keys()})
