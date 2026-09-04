"""Authoritative Bank Market-Segment Mapping.

BANK-PROVIDED BUSINESS LOGIC — do not modify without bank/business-owner
confirmation. This module is the SINGLE authoritative implementation of the
market-segment classification. Downstream consumers (ETL, feature pipeline,
ML, APIs, dashboards) must import this module rather than re-implementing
the CASE/dict elsewhere.

Mapping source metadata (provided by the bank):
    Version:         TBD / Not provided
    Effective date:  TBD / Not provided
    Source:          Bank customer master (market_segment_code field)
    Owner:           TBD / Not provided
    Change procedure: TBD — escalate to bank data governance before editing
"""

from __future__ import annotations

# ── Bank-provided authoritative mapping (code → segment label) ──────────────
# Treat this dict as immutable business configuration.
MARKET_SEGMENT_CODE_TO_NAME: dict[int, str] = {
    30: "CIB",        # Corporate & Investment Banking
    40: "BB",         # Business Banking
    45: "SME",        # Small & Medium Enterprise
    50: "Enterprise", # Enterprise
    60: "Prestige",   # Prestige
    65: "Personal",   # Personal
    75: "Mass",       # Mass
    85: "Premier",    # Premier
    90: "Staff",      # Staff
    99: "Internal",   # Internal
}

# Fallback label for unknown / unmapped / missing codes (spec §9, §10).
UNKNOWN_SEGMENT = "Other"

# The official codes (single list, derived from the mapping above).
OFFICIAL_CODES: frozenset[int] = frozenset(MARKET_SEGMENT_CODE_TO_NAME.keys())

# All known labels, including the fallback.
ALL_SEGMENTS: tuple[str, ...] = tuple(
    sorted(set(MARKET_SEGMENT_CODE_TO_NAME.values())) + [UNKNOWN_SEGMENT]
)

# Metadata for audit / MRM. TBD until the bank provides authoritative values.
MAPPING_METADATA: dict[str, str] = {
    "name": "bank_market_segment_mapping",
    "source": "Bank customer master",
    "source_field": "market_segment_code",
    "version": "TBD / Not provided",
    "effective_date": "TBD / Not provided",
    "owner": "TBD / Not provided",
    "change_procedure": "TBD — escalate to bank data governance",
    "documentation": "docs/ml/market-segment-integration.md",
}


# ── Deterministic resolution helpers ─────────────────────────────────────────

def is_official_code(value: object) -> bool:
    """Return True only for a known, numeric official bank code."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value in OFFICIAL_CODES
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped) in OFFICIAL_CODES
    return False


def _coerce_code(value: object) -> int | None:
    """Best-effort coerce to an int code.

    Returns the official int code if the value is a valid, known code,
    otherwise None (so callers fall back to the unknown/fallback label).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value in OFFICIAL_CODES else None
    if isinstance(value, float) and value.is_integer():
        v = int(value)
        return v if v in OFFICIAL_CODES else None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            v = int(stripped)
            return v if v in OFFICIAL_CODES else None
    return None


def resolve_market_segment(value: object) -> str:
    """Deterministically map a market_segment_code to its segment label.

    Behaviour (explicit, auditable — spec §9, §10):
      * official numeric code (int or digit string) → its label
      * unknown code, non-numeric, blank, missing, NULL  → 'Other'
    The original source value is never discarded by callers; this function
    only returns the normalised label.
    """
    code = _coerce_code(value)
    if code is None:
        return UNKNOWN_SEGMENT
    return MARKET_SEGMENT_CODE_TO_NAME[code]


def is_unknown(value: object) -> bool:
    """Return True when a raw source value is not an official bank code.

    Useful for data-quality monitoring metrics such as
    ``unknown_market_segment_count`` / ``unknown_market_segment_rate``.
    """
    return _coerce_code(value) is None
