"""Hardcoded catalog of source systems, master-data streams, and the
physical tables that make up each stream.

For v0 only ``file_upload`` (single arbitrary file) and ``sap_s4hana``
(schema-aware multi-table) are populated in detail. The other systems
show as picker tiles but their schemas are intentionally empty until the
connector lands.

Three flavours of table in a stream:

  * ``primary``    — the spine of the entity. Required. Provides the row
                     identity (e.g. LFA1 for vendor).
  * ``extension``  — per-context attributes (per company code, per sales
                     org). Joined to the primary via a shared key. May be
                     required (LFB1 for vendor company-code data) or
                     optional (LFM1 for purchasing data).
  * ``lookup``     — addresses, contacts, partner functions. Optional but
                     enriches the joined record.

ORG_SETUP_TABLES sit *outside* a stream — they're the foundation reference
data (company codes, currencies, country list, etc.) that every stream
references for referential-integrity checks. Loaded once per ERP and reused.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


SYSTEMS: List[Dict[str, Any]] = [
    {
        "id": "file_upload",
        "label": "File upload",
        "description": "CSV / Excel / Parquet / Feather / JSON.",
        "icon": "upload",
        "status": "available",
    },
    {
        "id": "netsuite",
        "label": "NetSuite",
        "description": "Live SuiteQL extract via Token-Based Authentication (TBA).",
        "icon": "netsuite",
        "status": "available",
    },
    {
        "id": "sap_s4hana",
        "label": "SAP S/4HANA",
        "description": "Direct extract from SAP master-data tables.",
        "icon": "sap",
        "status": "available",
    },
    {
        "id": "oracle_fusion",
        "label": "Oracle Fusion",
        "description": "Oracle Fusion ERP master-data extract.",
        "icon": "oracle",
        "status": "coming_soon",
    },
    {
        "id": "workday",
        "label": "Workday",
        "description": "Workday HCM / Financials master data.",
        "icon": "workday",
        "status": "coming_soon",
    },
    {
        "id": "snowflake",
        "label": "Snowflake",
        "description": "Snowflake warehouse — direct SQL connection.",
        "icon": "snowflake",
        "status": "coming_soon",
    },
]


STREAMS: List[Dict[str, Any]] = [
    {"id": "customer", "label": "Customer Master", "description": "Customer / debtor master data."},
    {"id": "vendor", "label": "Vendor Master", "description": "Vendor / supplier / creditor master data."},
    {"id": "material", "label": "Material Master", "description": "Product, SKU, item master data."},
    {"id": "gl_account", "label": "GL Account Master", "description": "Chart of accounts / general ledger."},
    {"id": "employee", "label": "Employee Master", "description": "HR / workforce master data."},
    {"id": "cost_center", "label": "Cost Centre Master", "description": "Finance / cost-center reference data."},
]


# ─── Per-stream schemas ──────────────────────────────────────────────
# Each entry describes ONE physical table the client must extract for
# that (system, stream) combination. Fields:
#
#   id              short technical id used in URLs and on-disk filenames
#   label           human-readable name
#   role            'primary' | 'extension' | 'lookup'
#   required        bool — if true, missing it blocks downstream steps
#   join_key        the column(s) used to join into the primary (or None
#                   if this is the primary itself)
#   description     1-line plain-English explanation
#   expected_columns  a representative subset of the real schema (not
#                     exhaustive — the loader still accepts whatever
#                     columns the file has)

STREAM_SCHEMAS: Dict[tuple, List[Dict[str, Any]]] = {
    # ── SAP S/4HANA · Vendor Master ──────────────────────────────
    ("sap_s4hana", "vendor"): [
        {
            "id": "LFA1",
            "label": "Vendor General Data",
            "role": "primary",
            "required": True,
            "join_key": None,
            "description": "One row per vendor — name, address, search terms, deletion flag.",
            "expected_columns": ["LIFNR", "NAME1", "LAND1", "ORT01", "PSTLZ", "STCD1", "STCD2"],
        },
        {
            "id": "LFB1",
            "label": "Vendor Company Code Data",
            "role": "extension",
            "required": True,
            "join_key": "LIFNR",
            "description": "Per company-code vendor settings — reconciliation account, payment terms.",
            "expected_columns": ["LIFNR", "BUKRS", "AKONT", "ZTERM", "ZWELS", "FDGRV"],
        },
        {
            "id": "LFM1",
            "label": "Vendor Purchasing Organization Data",
            "role": "extension",
            "required": False,
            "join_key": "LIFNR",
            "description": "Per purchasing-org vendor settings — order currency, payment, terms.",
            "expected_columns": ["LIFNR", "EKORG", "WAERS", "ZTERM"],
        },
        {
            "id": "LFBK",
            "label": "Vendor Bank Details",
            "role": "lookup",
            "required": False,
            "join_key": "LIFNR",
            "description": "Bank accounts associated with each vendor.",
            "expected_columns": ["LIFNR", "BANKS", "BANKL", "BANKN", "BKONT"],
        },
        {
            "id": "ADRC",
            "label": "Vendor Addresses",
            "role": "lookup",
            "required": False,
            "join_key": "ADRNR",
            "description": "Normalized address records linked from LFA1.ADRNR.",
            "expected_columns": ["ADDRNUMBER", "NAME1", "STREET", "CITY1", "POST_CODE1", "COUNTRY"],
        },
    ],

    # ── SAP S/4HANA · Customer Master ────────────────────────────
    ("sap_s4hana", "customer"): [
        {
            "id": "KNA1",
            "label": "Customer General Data",
            "role": "primary",
            "required": True,
            "join_key": None,
            "description": "One row per customer — name, address, tax IDs.",
            "expected_columns": ["KUNNR", "NAME1", "LAND1", "ORT01", "PSTLZ", "STCD1", "STCD2"],
        },
        {
            "id": "KNB1",
            "label": "Customer Company Code Data",
            "role": "extension",
            "required": True,
            "join_key": "KUNNR",
            "description": "Per company-code customer settings — reconciliation account, payment terms.",
            "expected_columns": ["KUNNR", "BUKRS", "AKONT", "ZTERM", "MAHNA"],
        },
        {
            "id": "KNVV",
            "label": "Customer Sales Area Data",
            "role": "extension",
            "required": False,
            "join_key": "KUNNR",
            "description": "Per sales-org/distribution-channel/division customer settings.",
            "expected_columns": ["KUNNR", "VKORG", "VTWEG", "SPART", "WAERS", "INCO1"],
        },
        {
            "id": "KNBK",
            "label": "Customer Bank Details",
            "role": "lookup",
            "required": False,
            "join_key": "KUNNR",
            "description": "Bank accounts associated with each customer.",
            "expected_columns": ["KUNNR", "BANKS", "BANKL", "BANKN"],
        },
        {
            "id": "ADRC",
            "label": "Customer Addresses",
            "role": "lookup",
            "required": False,
            "join_key": "ADRNR",
            "description": "Normalized address records linked from KNA1.ADRNR.",
            "expected_columns": ["ADDRNUMBER", "NAME1", "STREET", "CITY1", "POST_CODE1", "COUNTRY"],
        },
    ],

    # ── SAP S/4HANA · Material Master (sketched) ─────────────────
    ("sap_s4hana", "material"): [
        {
            "id": "MARA",
            "label": "Material General Data",
            "role": "primary",
            "required": True,
            "join_key": None,
            "description": "One row per material — type, group, base UoM.",
            "expected_columns": ["MATNR", "MTART", "MATKL", "MEINS", "BRGEW", "NTGEW"],
        },
        {
            "id": "MAKT",
            "label": "Material Descriptions",
            "role": "extension",
            "required": True,
            "join_key": "MATNR",
            "description": "Long descriptions per language.",
            "expected_columns": ["MATNR", "SPRAS", "MAKTX"],
        },
        {
            "id": "MARC",
            "label": "Material Plant Data",
            "role": "extension",
            "required": False,
            "join_key": "MATNR",
            "description": "Per-plant material settings — procurement type, MRP, batches.",
            "expected_columns": ["MATNR", "WERKS", "BESKZ", "DISPO", "EKGRP"],
        },
        {
            "id": "MBEW",
            "label": "Material Valuation",
            "role": "extension",
            "required": False,
            "join_key": "MATNR",
            "description": "Per-valuation-area cost data.",
            "expected_columns": ["MATNR", "BWKEY", "VPRSV", "VERPR", "STPRS"],
        },
    ],

    # ── SAP S/4HANA · GL Account Master ──────────────────────────
    ("sap_s4hana", "gl_account"): [
        {
            "id": "SKA1",
            "label": "G/L Account Chart-of-Accounts Data",
            "role": "primary",
            "required": True,
            "join_key": None,
            "description": "One row per GL account at the chart-of-accounts level.",
            "expected_columns": ["KTOPL", "SAKNR", "XBILK", "KTOKS"],
        },
        {
            "id": "SKAT",
            "label": "G/L Account Descriptions",
            "role": "extension",
            "required": True,
            "join_key": "SAKNR",
            "description": "Long and short descriptions per language.",
            "expected_columns": ["SPRAS", "KTOPL", "SAKNR", "TXT20", "TXT50"],
        },
        {
            "id": "SKB1",
            "label": "G/L Account Company Code Data",
            "role": "extension",
            "required": False,
            "join_key": "SAKNR",
            "description": "Per company-code GL account behavior.",
            "expected_columns": ["BUKRS", "SAKNR", "WAERS", "MWSKZ", "XOPVW"],
        },
    ],

    # ── NetSuite · Customer Master ────────────────────────────────
    # NetSuite stores customer data across several record types. The
    # ``id`` field on each entry is the SuiteQL table/record name; the
    # connector translates it into a SELECT * FROM <id> query.
    ("netsuite", "customer"): [
        {
            "id": "customer",
            "label": "Customer Record",
            "role": "primary",
            "required": True,
            "join_key": None,
            "description": "One row per customer entity — name, email, status, currency.",
            "expected_columns": ["id", "entityid", "companyname", "email", "phone", "isinactive", "datecreated"],
        },
        {
            "id": "customeraddressbook",
            "label": "Customer Addresses",
            "role": "lookup",
            "required": False,
            "join_key": "entity",
            "description": "Address book entries linked to customer records.",
            "expected_columns": ["entity", "addr1", "addr2", "city", "state", "zip", "country"],
        },
        {
            "id": "customercategory",
            "label": "Customer Categories",
            "role": "lookup",
            "required": False,
            "join_key": "id",
            "description": "Reference list of customer segmentation categories.",
            "expected_columns": ["id", "name", "isinactive"],
        },
        {
            "id": "subsidiary",
            "label": "Subsidiaries",
            "role": "lookup",
            "required": False,
            "join_key": None,
            "description": "Legal entities the customer can belong to (OneWorld accounts).",
            "expected_columns": ["id", "name", "country", "currency", "isinactive"],
        },
    ],

    # ── NetSuite · Vendor Master ──────────────────────────────────
    ("netsuite", "vendor"): [
        {
            "id": "vendor",
            "label": "Vendor Record",
            "role": "primary",
            "required": True,
            "join_key": None,
            "description": "One row per vendor — name, email, phone, currency, terms.",
            "expected_columns": ["id", "entityid", "companyname", "email", "phone", "currency", "terms", "isinactive"],
        },
        {
            "id": "vendoraddressbook",
            "label": "Vendor Addresses",
            "role": "lookup",
            "required": False,
            "join_key": "entity",
            "description": "Address book entries linked to vendor records.",
            "expected_columns": ["entity", "addr1", "city", "state", "zip", "country"],
        },
        {
            "id": "vendorcategory",
            "label": "Vendor Categories",
            "role": "lookup",
            "required": False,
            "join_key": "id",
            "description": "Vendor segmentation reference data.",
            "expected_columns": ["id", "name", "isinactive"],
        },
    ],

    # ── NetSuite · Material / Item Master ─────────────────────────
    ("netsuite", "material"): [
        {
            "id": "item",
            "label": "Item Record",
            "role": "primary",
            "required": True,
            "join_key": None,
            "description": "All item types (inventory, service, kit, assembly).",
            "expected_columns": ["id", "itemid", "displayname", "itemtype", "isinactive", "baseprice"],
        },
        {
            "id": "inventoryitem",
            "label": "Inventory Item Detail",
            "role": "extension",
            "required": False,
            "join_key": "id",
            "description": "Additional fields for inventory-tracked items.",
            "expected_columns": ["id", "averagecost", "lastpurchaseprice", "quantityonhand"],
        },
    ],

    # ── NetSuite · Employee Master ────────────────────────────────
    ("netsuite", "employee"): [
        {
            "id": "employee",
            "label": "Employee Record",
            "role": "primary",
            "required": True,
            "join_key": None,
            "description": "One row per employee — name, email, title, hire date.",
            "expected_columns": ["id", "entityid", "firstname", "lastname", "email", "title", "hiredate", "isinactive"],
        },
    ],

    # ── NetSuite · GL Account Master ──────────────────────────────
    ("netsuite", "gl_account"): [
        {
            "id": "account",
            "label": "GL Account Record",
            "role": "primary",
            "required": True,
            "join_key": None,
            "description": "Chart of accounts — account number, type, currency.",
            "expected_columns": ["id", "acctnumber", "accountsearchdisplayname", "accttype", "currency", "isinactive"],
        },
    ],
}


# ─── Organisation setup / reference tables per ERP ───────────────────

ORG_SETUP_TABLES: Dict[str, List[Dict[str, Any]]] = {
    "sap_s4hana": [
        {
            "id": "T001",
            "label": "Company Codes",
            "description": "Legal entities. Referenced by every vendor / customer / GL row via BUKRS.",
            "expected_columns": ["BUKRS", "BUTXT", "LAND1", "WAERS"],
        },
        {
            "id": "T001W",
            "label": "Plants",
            "description": "Sites / plants. Referenced by material data via WERKS.",
            "expected_columns": ["WERKS", "NAME1", "LAND1", "ORT01"],
        },
        {
            "id": "TVKO",
            "label": "Sales Organizations",
            "description": "Referenced by customer sales-area data via VKORG.",
            "expected_columns": ["VKORG", "VKOTXT", "BUKRS"],
        },
        {
            "id": "T024",
            "label": "Purchasing Organizations",
            "description": "Referenced by vendor purchasing data via EKORG.",
            "expected_columns": ["EKORG", "EKOTX", "BUKRS"],
        },
        {
            "id": "T005",
            "label": "Country Codes",
            "description": "Valid ISO countries. Referenced by LAND1 across all masters.",
            "expected_columns": ["LAND1", "LANDX", "INTCA"],
        },
        {
            "id": "TCURC",
            "label": "Currency Codes",
            "description": "Valid currencies. Referenced by WAERS.",
            "expected_columns": ["WAERS", "ISOCD", "LTEXT"],
        },
    ],
    "oracle_fusion": [],
    "workday": [],
    "snowflake": [],
    "file_upload": [],
}


# ─── Lookup helpers ──────────────────────────────────────────────────


def get_system(system_id: str) -> Optional[Dict[str, Any]]:
    return next((s for s in SYSTEMS if s["id"] == system_id), None)


def get_stream(stream_id: str) -> Optional[Dict[str, Any]]:
    return next((s for s in STREAMS if s["id"] == stream_id), None)


def get_stream_tables(system_id: str, stream_id: str) -> List[Dict[str, Any]]:
    """Return the table specs for this (system, stream) combination.

    For ``file_upload`` we synthesize a single primary table so the rest
    of the code can treat every project uniformly.
    """
    if system_id == "file_upload":
        return [
            {
                "id": "primary",
                "label": "Uploaded file",
                "role": "primary",
                "required": True,
                "join_key": None,
                "description": "Single uploaded file — any tabular format.",
                "expected_columns": [],
            }
        ]
    return list(STREAM_SCHEMAS.get((system_id, stream_id), []))


def get_org_setup_tables(system_id: str) -> List[Dict[str, Any]]:
    return list(ORG_SETUP_TABLES.get(system_id, []))
