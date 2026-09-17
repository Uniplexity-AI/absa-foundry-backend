"""Canonical ingest contract — the single source of truth for how inbound data
must be shaped before it lands in Postgres.

Two consumers read this module:

* ``GET /api/v1/ingest/schema`` — the My Customers page renders the returned
  field catalogue as a column-mapping table, so an operator can see exactly
  what each CSV column maps to and what format that target field expects.
* ``etl.ingest.loader`` — validates and normalises every inbound row against
  the same rules, so the UI and the loader can never disagree.

Datasets (see :data:`DATASETS`):

``customers``
    ``public.customers_clean`` — one row per customer, keyed on ``customer_id``.
    Loader stamps ``loaded_at`` / ``batch_id``.
``customer_features``
    ``public.customer_features`` — one row per customer *per snapshot date*,
    keyed on ``(customer_id, as_of_date)``. This is the feature-store extract
    produced by the feature pipeline; the loader stamps ``computed_at`` when
    the extract omits it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Literal

TARGET_TABLE = "public.customers_clean"
REJECTED_TABLE = "public.customer_ingest_rejected"
CUSTOMER_ID_FIELD = "customer_id"

DType = Literal["string", "date", "datetime", "enum", "boolean", "integer", "decimal"]


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

_MONTH_NAME_FORMATS = ("%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d %B, %Y", "%b %d, %Y")
# Year-first forms observed in the core banking extracts.
_ISO_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d")
# Day-first is the Absa house convention; used only when nothing else decides.
_DAY_FIRST_FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y")
_MONTH_FIRST_FORMATS = ("%m-%d-%Y", "%m/%d/%Y")

#: The core banking extracts use the separator to carry the day/month order —
#: verified against public.customers_core: every ``NN-NN-NNNN`` value that can
#: only be month-first (second component > 12) is dash-separated, and every
#: ``NN/NN/NNNN`` value that can only be day-first (first component > 12) is
#: slash-separated. Without this hint ~40% of numeric dates are ambiguous.
_NUMERIC_SEPARATOR_HINTS: dict[str, tuple[str, ...]] = {
    "-": _MONTH_FIRST_FORMATS,   # MM-DD-YYYY
    "/": _DAY_FIRST_FORMATS,     # DD-MM-YYYY
}

#: ``2016-09-09 00:00:00`` / ``2016-09-09T00:00:00`` — keep only the date part.
_DATETIME_PREFIX_RE = re.compile(r"^(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})[ T]\d{1,2}:\d{2}")


class DateParseError(ValueError):
    """Raised when a value cannot be interpreted as a date."""


def parse_date(value: Any) -> date:
    """Parse the date formats seen in Absa source systems.

    Handles ISO (``2016-09-09``), dotted year-first (``1966.03.12``),
    day-first (``30 Apr 2017``), month-first (``03-20-2016``) and compact
    (``20160909``) forms.

    Numeric ``X-Y-Z`` values are resolved in this order:

    1. a component greater than 12 decides the order outright;
    2. otherwise the separator decides (``-`` month-first, ``/`` day-first —
       the convention the core extracts actually use);
    3. otherwise day-first, the documented bank convention.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        raise DateParseError("empty date")

    text = str(value).strip()
    if not text:
        raise DateParseError("empty date")

    datetime_prefix = _DATETIME_PREFIX_RE.match(text)
    if datetime_prefix:
        text = datetime_prefix.group(1)

    for fmt in (*_ISO_FORMATS, *_MONTH_NAME_FORMATS):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    numeric = re.fullmatch(r"(\d{1,4})([-/.])(\d{1,2})\2(\d{1,4})", text)
    if numeric:
        first, separator, second, _third = numeric.groups()
        if len(first) == 4:
            candidates = _ISO_FORMATS
        elif int(first) > 12:
            candidates = _DAY_FIRST_FORMATS
        elif int(second) > 12:
            candidates = _MONTH_FIRST_FORMATS
        else:
            candidates = _NUMERIC_SEPARATOR_HINTS.get(separator, _DAY_FIRST_FORMATS)
        for fmt in candidates:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue

    raise DateParseError(f"unrecognised date format: {text!r}")


# ---------------------------------------------------------------------------
# Datetime parsing
# ---------------------------------------------------------------------------

_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S",
)


def parse_datetime(value: Any) -> datetime:
    """Parse a timestamp, falling back to date parsing when no time is present."""
    if isinstance(value, datetime):
        return value
    if value is None:
        raise DateParseError("empty timestamp")

    text = str(value).strip()
    if not text:
        raise DateParseError("empty timestamp")

    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    # A bare date is a valid timestamp at midnight.
    return datetime.combine(parse_date(text), datetime.min.time())


# ---------------------------------------------------------------------------
# Boolean parsing
# ---------------------------------------------------------------------------

_TRUE_VALUES = frozenset({"true", "t", "yes", "y", "1", "active", "on"})
_FALSE_VALUES = frozenset({"false", "f", "no", "n", "0", "inactive", "off"})


def parse_boolean(value: Any) -> bool:
    """Parse the boolean spellings produced by SQL clients and Excel exports."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    raise FieldValueError(f"{value!r} is not a boolean (use TRUE/FALSE)")


# ---------------------------------------------------------------------------
# Field catalogue
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CustomerField:
    """One target column of ``public.customers_clean`` plus its ingest rules."""

    name: str
    label: str
    dtype: DType
    required: bool = False
    format: str = ""
    max_length: int | None = None
    regex: str | None = None
    allowed: tuple[str, ...] = ()
    value_aliases: dict[str, str] = field(default_factory=dict)
    example: str = ""
    notes: str = ""
    aliases: tuple[str, ...] = ()

    def describe(self) -> dict[str, Any]:
        """Serialise for ``GET /api/v1/ingest/schema``."""
        return {
            "name": self.name,
            "label": self.label,
            "type": self.dtype,
            "required": self.required,
            "format": self.format,
            "max_length": self.max_length,
            "regex": self.regex,
            "allowed_values": list(self.allowed),
            "accepted_aliases": sorted({*self.aliases}),
            "value_aliases": dict(self.value_aliases),
            "example": self.example,
            "notes": self.notes,
        }


def F(name: str, dtype: DType, fmt: str, **kwargs: Any) -> CustomerField:
    """Compact constructor for the feature-store catalogue below.

    Keeps each field a single readable line: column, type, expected format,
    then only the options that actually apply.
    """
    kwargs.setdefault("label", _humanise(name))
    return CustomerField(name=name, dtype=dtype, format=fmt, **kwargs)


_ACRONYMS = {
    "id": "ID", "txn": "Txn", "kyc": "KYC", "atm": "ATM", "ussd": "USSD",
    "pos": "POS", "stddev": "Std Dev", "pct": "%", "d": "(d)", "mo": "Month",
    "eng": "Engagement", "behav": "Behaviour", "fin": "Financial", "chan": "Channel",
    "temp": "Temporal", "rel": "Relationship", "prof": "Profile", "amt": "Amount",
    "avg": "Average", "est": "Estimate", "max": "Max", "min": "Min",
}


def _humanise(column: str) -> str:
    """``days_since_last_txn`` → ``Days Since Last Txn`` (acronym-aware)."""
    words = []
    for token in str(column).split("_"):
        lowered = token.lower()
        if lowered in _ACRONYMS:
            words.append(_ACRONYMS[lowered])
        elif re.fullmatch(r"\d+[a-z]+", lowered):
            words.append(lowered.upper())
        elif lowered:
            words.append(lowered.capitalize())
    return " ".join(words) or column


#: The gender/status style enums used by the customer master dataset.
_GENDER_VALUES = ("MALE", "FEMALE", "UNKNOWN")

CUSTOMER_FIELDS: tuple[CustomerField, ...] = (
    CustomerField(
        name="customer_id",
        label="Customer ID",
        dtype="string",
        required=True,
        format="1–64 characters, letters/digits/._-/ only",
        max_length=64,
        regex=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$",
        example="CUST0000001",
        notes="Primary key of customers_clean. Matching IDs are updated, new IDs are inserted.",
        aliases=(
            "customer_id", "customerid", "customer_number", "customernumber", "customer_no",
            "cust_id", "custid", "cust_ref", "customer_ref", "client_id",
        ),
    ),
    CustomerField(
        name="account_number",
        label="Account Number",
        dtype="string",
        format="1–64 characters, letters/digits/-/. only",
        max_length=64,
        regex=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$",
        example="ZMK-8820-192",
        notes=(
            "Primary account of the customer. When omitted, the profile falls back "
            "to the earliest account in public.accounts_clean."
        ),
        aliases=(
            "account_number", "accountnumber", "account_no", "accountno", "acct_no",
            "acctno", "account_id", "accountid", "primary_account", "primary_account_number",
        ),
    ),
    CustomerField(
        name="status",
        label="Account Status",
        dtype="enum",
        required=True,
        format="one of: Active, Dormant, Closed, Suspended",
        allowed=("Active", "Dormant", "Closed", "Suspended"),
        value_aliases={
            "a": "Active", "active": "Active", "open": "Active", "1": "Active",
            "d": "Dormant", "dormant": "Dormant", "inactive": "Dormant", "2": "Dormant",
            "c": "Closed", "closed": "Closed", "churned": "Closed", "3": "Closed",
            "s": "Suspended", "suspended": "Suspended", "blocked": "Suspended",
        },
        example="Active",
        notes="Churn label source (pilot_data_config.churn_label). Dormant/Closed count as churned.",
        aliases=(
            "status", "customer_status", "customerstatus", "account_status", "state",
            "lifecycle_status", "rel_customer_status", "relcustomerstatus",
        ),
    ),
    CustomerField(
        name="full_name",
        label="Full Name",
        dtype="string",
        format="free text, max 128 characters",
        max_length=128,
        example="Chris Curtis",
        notes="Concatenate first_name + family_name upstream if the core system splits them.",
        aliases=("full_name", "fullname", "name", "customer_name", "customername", "customer_full_name"),
    ),
    CustomerField(
        name="date_of_birth",
        label="Date of Birth",
        dtype="date",
        format="YYYY-MM-DD (accepts DD-MM-YYYY, MM-DD-YYYY, DD Mon YYYY)",
        example="1950-01-14",
        notes="Stored as DATE. Mixed core formats are normalised on ingest.",
        aliases=("date_of_birth", "dateofbirth", "dob", "birth_date", "birthdate"),
    ),
    CustomerField(
        name="national_id",
        label="ID Number (NRC)",
        dtype="string",
        format="national identity number, e.g. 123456/78/9 (free text, 4–32 characters)",
        max_length=32,
        regex=r"^[A-Za-z0-9][A-Za-z0-9/.\-]{3,31}$",
        example="994022/11/1",
        notes=(
            "NRC / national ID. Kept as text because the format differs per country. "
            "No pilot source supplies it yet — it shows as 'Not on file' until a source is mapped."
        ),
        aliases=(
            "national_id", "nationalid", "nrc", "nrc_number", "nrcnumber", "id_number",
            "idnumber", "nin", "national_id_number", "identity_number", "identitynumber",
        ),
    ),
    CustomerField(
        name="gender",
        label="Gender",
        dtype="enum",
        format="MALE | FEMALE | UNKNOWN",
        allowed=_GENDER_VALUES,
        value_aliases={
            "m": "MALE", "male": "MALE", "1": "MALE",
            "f": "FEMALE", "female": "FEMALE", "2": "FEMALE",
            "u": "UNKNOWN", "unknown": "UNKNOWN", "": "UNKNOWN",
        },
        example="FEMALE",
        notes="Core systems send M/F; ingest standardises to MALE/FEMALE (REAL-DATA-MAPPING §gender).",
        aliases=("gender", "sex"),
    ),
    CustomerField(
        name="branch_code",
        label="Branch Code",
        dtype="string",
        format="uppercase, 1–16 characters (A–Z, 0–9, -)",
        max_length=16,
        regex=r"^[A-Z0-9-]{1,16}$",
        example="BR001",
        notes="Lower-case input is upper-cased. Join key for the branch dimension.",
        aliases=("branch_code", "branchcode", "branch", "branch_id", "branchid", "branch_number", "branch_no"),
    ),
    CustomerField(
        name="customer_since_date",
        label="Customer Since",
        dtype="date",
        format="YYYY-MM-DD (accepts DD-MM-YYYY, MM-DD-YYYY, DD Mon YYYY)",
        example="2016-03-20",
        notes="Core customer_creation_date / activation_date. Drives tenure features.",
        aliases=(
            "customer_since_date", "customersincedate", "customer_since", "since_date",
            "activation_date", "activationdate", "customer_creation_date",
            "customercreationdate", "opened_date", "openeddate", "onboarding_date",
            "date_opened", "start_date",
        ),
    ),
    CustomerField(
        name="kyc_tier",
        label="KYC Tier",
        dtype="string",
        format="TIER_1 … TIER_4 (upper-cased on ingest)",
        max_length=16,
        regex=r"^[A-Z0-9_]{1,16}$",
        example="TIER_1",
        notes="Core kyc_status values such as 'Verified' are mapped to a tier where possible.",
        aliases=("kyc_tier", "kyctier", "kyc_status", "kycstatus", "kyc", "kyc_level", "kyclevel"),
    ),
    CustomerField(
        name="nationality",
        label="Nationality",
        dtype="string",
        format="ISO 3166-1 alpha-2 code, upper-cased (e.g. ZM, ZA, MW)",
        max_length=64,
        example="ZM",
        notes="Core 'country' / 'nationalitycode' columns map here.",
        aliases=("nationality", "country", "country_code", "countrycode", "nationality_code",
                 "nationalitycode", "iso_country"),
    ),
    CustomerField(
        name="market_segment_code",
        label="Market Segment",
        dtype="enum",
        format="one of the 8 Absa segment codes",
        allowed=("30", "40", "45", "50", "60", "65", "75", "85"),
        value_aliases={
            "cib": "30", "corporate": "30", "corporate & investment banking": "30",
            "bb": "40", "business banking": "40",
            "sme": "45", "small & medium enterprise": "45",
            "enterprise": "50",
            "prestige": "60",
            "personal": "65",
            "mass": "75",
            "premier": "85",
        },
        example="60",
        notes="Absa market-segment taxonomy (shared/constants/market_segments.py). Label is resolved on write.",
        aliases=("market_segment_code", "marketsegmentcode", "market_segment", "marketsegment",
                 "segment", "segment_code", "segmentcode"),
    ),
)

FIELDS_BY_NAME: dict[str, CustomerField] = {f.name: f for f in CUSTOMER_FIELDS}

# Columns written on every load — data columns plus loader-stamped metadata.
DATA_COLUMNS: tuple[str, ...] = tuple(f.name for f in CUSTOMER_FIELDS)
META_COLUMNS: tuple[str, ...] = ("loaded_at", "batch_id")


# ---------------------------------------------------------------------------
# Customer feature store — public.customer_features
# ---------------------------------------------------------------------------
# One row per customer per snapshot date. The catalogue mirrors the feature
# pipeline's output contract (database/feature_store/001_customer_features.sql);
# formats are taken from the real column types so an operator sees exactly what
# each column must look like before a load.
#
# ``id`` is deliberately absent: it is a surrogate key generated by Postgres, so
# a CSV column named ``id`` correctly maps to nothing.

_FEATURE_INT = "whole number (no decimals)"
_FEATURE_NUM = "decimal number"
_FEATURE_BOOL = "TRUE / FALSE"
_FEATURE_DATE = "YYYY-MM-DD"
_FEATURE_TS = "YYYY-MM-DD HH:MM:SS"

FEATURE_FIELDS: tuple[CustomerField, ...] = (
    # ── Identity & snapshot ──
    F("customer_id", "string", "1–64 characters, letters/digits/._-/ only",
      required=True, max_length=64, regex=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$",
      example="CUST0001766", aliases=("customer_id", "customerid", "customer_number", "cust_id")),
    F("as_of_date", "date", _FEATURE_DATE, required=True, example="2026-07-19",
      notes="Snapshot the features were computed for. Part of the natural key.",
      aliases=("as_of_date", "asofdate", "snapshot_date", "feature_date", "as_of")),
    F("computed_at", "datetime", _FEATURE_TS,
      notes="Stamped with the load time when the extract omits it.",
      aliases=("computed_at", "computedat", "computed_on")),
    # ── Transaction cadence ──
    F("days_since_last_txn", "integer", _FEATURE_INT),
    F("days_since_first_txn", "integer", _FEATURE_INT),
    F("txn_count_30d", "integer", _FEATURE_INT),
    F("txn_count_90d", "integer", _FEATURE_INT),
    F("txn_count_180d", "integer", _FEATURE_INT),
    F("txn_count_365d", "integer", _FEATURE_INT),
    F("avg_days_between_txn", "decimal", _FEATURE_NUM),
    F("distinct_channels_90d", "integer", _FEATURE_INT),
    F("distinct_txn_types_90d", "integer", _FEATURE_INT),
    F("dominant_channel", "enum", "one of ATM | BRANCH | MOBILE_APP | ONLINE_BANKING | POS | USSD",
      allowed=("ATM", "BRANCH", "MOBILE_APP", "ONLINE_BANKING", "POS", "USSD"), example="USSD",
      aliases=("dominant_channel", "dominantchannel", "txn_dominant_channel_last_90_days")),
    # ── Transaction amounts ──
    F("total_amount_90d", "decimal", _FEATURE_NUM),
    F("avg_amount_90d", "decimal", _FEATURE_NUM),
    F("total_amount_180d", "decimal", _FEATURE_NUM),
    F("amount_growth_ratio", "decimal", _FEATURE_NUM),
    F("amount_stddev_90d", "decimal", _FEATURE_NUM),
    F("credit_sum_30d", "decimal", _FEATURE_NUM),
    F("debit_sum_30d", "decimal", _FEATURE_NUM),
    F("credit_to_debit_ratio_90d", "decimal", _FEATURE_NUM),
    F("balance_trend_90d", "enum", "RISING | STABLE | FALLING",
      allowed=("RISING", "STABLE", "FALLING"), example="STABLE"),
    F("monthly_income_estimate", "decimal", _FEATURE_NUM),
    F("has_salary_credit", "boolean", _FEATURE_BOOL),
    # ── Behavioural ──
    F("behav_txn_count_7d", "integer", _FEATURE_INT),
    F("behav_active_days_90d", "integer", _FEATURE_INT),
    F("behav_inactive_days_90d", "integer", _FEATURE_INT),
    F("behav_recency_score", "decimal", _FEATURE_NUM),
    F("behav_frequency_score", "decimal", _FEATURE_NUM),
    F("behav_diversity_score", "decimal", _FEATURE_NUM),
    F("behav_activity_consistency", "decimal", _FEATURE_NUM),
    # ── Financial ──
    F("fin_total_credit_90d", "decimal", _FEATURE_NUM),
    F("fin_total_debit_90d", "decimal", _FEATURE_NUM),
    F("fin_median_txn_amount_90d", "decimal", _FEATURE_NUM),
    F("fin_salary_consistency", "decimal", _FEATURE_NUM),
    F("fin_income_growth", "decimal", _FEATURE_NUM),
    # ── Channel mix ──
    F("chan_mobile_ratio_90d", "decimal", "decimal between 0 and 1"),
    F("chan_atm_ratio_90d", "decimal", "decimal between 0 and 1"),
    F("chan_branch_ratio_90d", "decimal", "decimal between 0 and 1"),
    F("chan_digital_adoption_score", "decimal", "decimal between 0 and 1"),
    F("chan_channel_entropy", "decimal", _FEATURE_NUM),
    # ── Tenure & lifecycle ──
    F("customer_tenure_days", "integer", _FEATURE_INT,
      notes="Tenure is also derived on the profile when this is null."),
    F("customer_segment", "string", "text (max 64 characters)", max_length=64),
    F("age_years", "integer", _FEATURE_INT),
    F("onboarding_channel", "string", "text (max 32 characters)", max_length=32),
    F("target_lifecycle_stage", "enum", "NEW | ACTIVE | GROWING | AT_RISK | DORMANT | CHURNED",
      allowed=("NEW", "ACTIVE", "GROWING", "AT_RISK", "DORMANT", "CHURNED"), example="GROWING",
      notes="Lifecycle label from the state engine; the column is additive (migration 015)."),
    F("engagement_score", "decimal", "decimal between 0 and 100"),
    F("txn_frequency_trend", "decimal", _FEATURE_NUM),
    F("inactivity_streak_days", "integer", _FEATURE_INT),
    F("balance_growth_pct", "decimal", "percentage change, e.g. -44.19",
      notes="Additive column (migration 015)."),
    # ── Temporal patterns ──
    F("temp_weekend_txn_ratio_90d", "decimal", "decimal between 0 and 1"),
    F("temp_weekday_txn_ratio_90d", "decimal", "decimal between 0 and 1"),
    F("temp_morning_activity_ratio_90d", "decimal", "decimal between 0 and 1"),
    F("temp_afternoon_activity_ratio_90d", "decimal", "decimal between 0 and 1"),
    F("temp_evening_activity_ratio_90d", "decimal", "decimal between 0 and 1"),
    F("temp_payday_activity_ratio_90d", "decimal", "decimal between 0 and 1"),
    # ── Risk ──
    F("risk_high_value_txn_ratio_90d", "decimal", "decimal between 0 and 1"),
    F("risk_txn_volatility_90d", "decimal", _FEATURE_NUM),
    F("risk_reversal_ratio_90d", "decimal", "decimal between 0 and 1"),
    F("risk_cash_heavy_ratio_90d", "decimal", "decimal between 0 and 1"),
    F("risk_unusual_channel_flag", "boolean", _FEATURE_BOOL),
    F("risk_dormant_indicator", "boolean", _FEATURE_BOOL),
    # ── Relationship / product holdings ──
    F("rel_customer_status", "enum", "Active | Dormant | Closed | Suspended",
      allowed=("Active", "Dormant", "Closed", "Suspended"), example="Active"),
    F("rel_accounts_active", "integer", _FEATURE_INT),
    F("rel_has_loan", "boolean", _FEATURE_BOOL),
    F("rel_has_savings", "boolean", _FEATURE_BOOL),
    F("rel_products_owned", "integer", _FEATURE_INT),
    F("rel_has_card", "boolean", _FEATURE_BOOL),
    F("rel_card_count", "integer", _FEATURE_INT),
    F("rel_has_unactivated_card", "boolean", _FEATURE_BOOL),
    F("rel_card_expiring_30d", "integer", _FEATURE_INT),
    F("rel_card_types", "integer", _FEATURE_INT),
    # ── Digital engagement ──
    F("eng_login_count_7d", "integer", _FEATURE_INT),
    F("eng_login_count_30d", "integer", _FEATURE_INT),
    F("eng_digital_platform_preference", "string", "text (max 32 characters)", max_length=32),
    F("eng_avg_session_duration_30d", "decimal", _FEATURE_NUM),
    # ── Profile / demographics ──
    F("prof_age_band", "string", "text (max 16 characters)", max_length=16),
    F("prof_primary_branch", "string", "text (max 16 characters)", max_length=16),
    F("prof_kyc_tier", "string", "TIER_1 … TIER_4", max_length=16),
    F("prof_nationality", "string", "ISO 3166-1 alpha-2 code (e.g. ZM)", max_length=64),
    F("prof_employment_status", "string", "text (max 32 characters)", max_length=32),
    F("prof_education_level", "string", "text (max 32 characters)", max_length=32),
    F("prof_declared_vs_observed_income_ratio", "decimal", _FEATURE_NUM),
    # ── Market segmentation ──
    # NOTE: no "market_segment" alias on the code field. On this table the code
    # (30/40/60...) and the label are two distinct columns, so aliasing one to
    # the other would swallow the export's real market_segment column.
    F("market_segment_code", "string", "Absa segment code (30, 40, 45, 50, 60, 65, 75, 85)",
      max_length=16, example="60",
      aliases=("marketsegmentcode", "segment_code")),
    F("market_segment", "string", "segment label, resolved from the code on write if blank",
      max_length=32, aliases=("marketsegment", "market_segment_label", "segment_label")),
)

FEATURE_FIELDS_BY_NAME: dict[str, CustomerField] = {f.name: f for f in FEATURE_FIELDS}


# ---------------------------------------------------------------------------
# Dataset registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DatasetSpec:
    """A loadable target table: its contract, natural key and stamped columns."""

    key: str
    label: str
    table: str
    description: str
    fields: tuple[CustomerField, ...]
    key_columns: tuple[str, ...]
    notes: str = ""
    #: column → "now" (stamp with load time) or "batch" (stamp with the batch id)
    stamps: dict[str, str] = field(default_factory=dict)

    @property
    def fields_by_name(self) -> dict[str, CustomerField]:
        return {f.name: f for f in self.fields}

    @property
    def data_columns(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)

    @property
    def alias_index(self) -> dict[str, str]:
        """Normalised source-column name → field name.

        Field names are registered before aliases, and aliases in field order,
        so a column whose name *is* a declared field always wins over some other
        field's alias. Without this, ``market_segment`` would be captured by the
        ``market_segment_code`` alias rather than its own field.
        """
        index: dict[str, str] = {}
        for spec in self.fields:
            index.setdefault(_normalise_column(spec.name), spec.name)
        for spec in self.fields:
            for alias in spec.aliases:
                index.setdefault(_normalise_column(alias), spec.name)
        return index

    def describe(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "table": self.table,
            "description": self.description,
            "notes": self.notes,
            "key_columns": list(self.key_columns),
            "field_count": len(self.fields),
            "fields": [f.describe() for f in self.fields],
        }


DATASETS: dict[str, DatasetSpec] = {
    "customers": DatasetSpec(
        key="customers",
        label="Customer Master",
        table=TARGET_TABLE,
        description="One row per customer — identity, branch, KYC and status.",
        fields=CUSTOMER_FIELDS,
        key_columns=("customer_id",),
        notes="Existing customer IDs are updated in place; new IDs are inserted.",
        stamps={"loaded_at": "now", "batch_id": "batch"},
    ),
    "customer_features": DatasetSpec(
        key="customer_features",
        label="Customer Features (snapshot)",
        table="public.customer_features",
        description=(
            "One row per customer per snapshot date — the feature-store extract "
            "produced by the feature pipeline. Matches the column set exported "
            "from public.customer_features."
        ),
        fields=FEATURE_FIELDS,
        key_columns=("customer_id", "as_of_date"),
        notes=(
            "Keyed on (customer_id, as_of_date): re-loading the same snapshot "
            "updates those rows rather than duplicating them."
        ),
        stamps={"computed_at": "now"},
    ),
}

DEFAULT_DATASET = "customers"


def get_dataset(key: str | None = None) -> DatasetSpec:
    """Resolve a dataset by key, falling back to the customer master."""
    spec = DATASETS.get(str(key or DEFAULT_DATASET))
    if spec is None:
        raise KeyError(f"Unknown ingest dataset {key!r}. Available: {', '.join(DATASETS)}")
    return spec


# ---------------------------------------------------------------------------
# Column auto-mapping
# ---------------------------------------------------------------------------

def _normalise_column(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").strip().lower())


def auto_map(columns: Iterable[str], dataset: str | None = None) -> dict[str, str | None]:
    """Propose a source-column → target-field mapping for one dataset.

    Exact (normalised) matches against a field name or one of its documented
    aliases win; unmatched columns are left unmapped for the operator to fix.
    A target is only claimed once, so two source columns never collide.
    """
    spec = get_dataset(dataset)
    index = spec.alias_index

    mapping: dict[str, str | None] = {}
    taken: set[str] = set()
    for column in columns:
        target = index.get(_normalise_column(column))
        if target and target not in taken:
            mapping[str(column)] = target
            taken.add(target)
        else:
            mapping[str(column)] = None
    return mapping


def describe_schema() -> dict[str, Any]:
    """Payload for ``GET /api/v1/ingest/schema``.

    ``datasets`` lists every loadable target; ``fields``/``target_table`` are
    kept so callers written against the single-dataset version still work.
    """
    default = get_dataset(DEFAULT_DATASET)
    return {
        "target_table": default.table,
        "rejected_table": REJECTED_TABLE,
        "primary_key": CUSTOMER_ID_FIELD,
        "default_dataset": DEFAULT_DATASET,
        "datasets": [spec.describe() for spec in DATASETS.values()],
        "load_modes": {
            "upsert": "Rows whose key columns already exist are updated in place.",
            "insert": "New key values are appended.",
        },
        "fields": [f.describe() for f in default.fields],
    }


# ---------------------------------------------------------------------------
# Value coercion
# ---------------------------------------------------------------------------

class FieldValueError(ValueError):
    """Raised when a single field value fails its contract."""


#: Code-like fields are normalised to upper case so downstream joins match.
_UPPERCASE_FIELDS = frozenset({"branch_code", "nationality", "kyc_tier"})


def _coerce_enum(spec: CustomerField, raw: str) -> str:
    key = raw.strip()
    if not key:
        raise FieldValueError("empty value")
    exact = {v.lower(): v for v in spec.allowed}.get(key.lower())
    if exact is not None:
        return exact
    alias = spec.value_aliases.get(key.lower())
    if alias is not None:
        return alias
    raise FieldValueError(f"{key!r} is not one of {', '.join(spec.allowed)}")


def coerce_value(spec: CustomerField, raw: Any) -> str | date | datetime | bool | int | float | None:
    """Normalise one raw source value to the canonical Postgres shape.

    Returns ``None`` for blank values. Raises :class:`FieldValueError` when the
    value is present but violates the field's documented format.
    """
    if raw is None:
        return None
    if isinstance(raw, float) and raw != raw:  # NaN
        return None

    text = str(raw).strip()
    if text == "" or text.lower() in {"null", "none", "nan", "n/a", "na"}:
        return None

    if spec.dtype == "date":
        try:
            return parse_date(text)
        except DateParseError as exc:
            raise FieldValueError(f"{text!r} is not a valid date ({exc})") from exc

    if spec.dtype == "datetime":
        try:
            return parse_datetime(text)
        except DateParseError as exc:
            raise FieldValueError(f"{text!r} is not a valid timestamp ({exc})") from exc

    if spec.dtype == "boolean":
        return parse_boolean(text)

    if spec.dtype == "enum":
        return _coerce_enum(spec, text)

    if spec.dtype == "integer":
        try:
            return int(float(text))
        except ValueError as exc:
            raise FieldValueError(f"{text!r} is not an integer") from exc

    if spec.dtype == "decimal":
        try:
            return float(text)
        except ValueError as exc:
            raise FieldValueError(f"{text!r} is not a number") from exc

    # string
    if spec.name in _UPPERCASE_FIELDS:
        text = text.upper()
    if spec.max_length is not None and len(text) > spec.max_length:
        raise FieldValueError(f"{len(text)} characters exceeds max_length {spec.max_length}")
    if spec.regex and not re.fullmatch(spec.regex, text):
        raise FieldValueError(f"{text!r} does not match {spec.regex}")
    return text


def coerce_row(
    row: dict[str, Any],
    mapping: dict[str, str | None],
    dataset: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Apply ``mapping`` to one source row for one dataset.

    Returns ``(record, errors)``. ``record`` holds only the fields that were
    mapped and coerced successfully; ``errors`` lists human-readable problems.
    """
    spec = get_dataset(dataset)
    fields_by_name = spec.fields_by_name

    record: dict[str, Any] = {}
    errors: list[str] = []

    for source_column, target in mapping.items():
        if not target:
            continue
        target_field = fields_by_name.get(target)
        if target_field is None:
            errors.append(f"{source_column}: unknown target field {target!r}")
            continue
        value = row.get(source_column)
        try:
            coerced = coerce_value(target_field, value)
        except FieldValueError as exc:
            errors.append(f"{source_column} -> {target_field.name}: {exc}")
            continue
        if coerced is not None:
            record[target_field.name] = coerced

    for field_spec in spec.fields:
        if field_spec.required and record.get(field_spec.name) is None:
            errors.append(f"{field_spec.label} ({field_spec.name}) is required but missing or empty")

    return record, errors


def validate_mapping(mapping: dict[str, str | None], dataset: str | None = None) -> list[str]:
    """Structural checks on a proposed mapping (before any row is processed)."""
    spec = get_dataset(dataset)
    fields_by_name = spec.fields_by_name

    errors: list[str] = []
    targets = [t for t in mapping.values() if t]

    unknown = sorted({t for t in targets if t not in fields_by_name})
    if unknown:
        errors.append(f"Unknown target field(s): {', '.join(unknown)}")

    duplicates = sorted({t for t in targets if targets.count(t) > 1})
    if duplicates:
        labels = ", ".join(
            fields_by_name[t].label if t in fields_by_name else t for t in duplicates
        )
        errors.append(f"More than one source column maps to: {labels}")

    for field_spec in spec.fields:
        if field_spec.required and field_spec.name not in targets:
            errors.append(
                f"{field_spec.label} ({field_spec.name}) is required but no source column is mapped to it"
            )

    return errors
