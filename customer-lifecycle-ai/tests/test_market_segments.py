"""Unit tests for the authoritative bank market-segment mapping.

Covers spec §11 requirements: every official mapping, unknown handling,
NULL/blank/non-numeric handling, and preservation of the original code.
The mapping itself is BANK-PROVIDED BUSINESS LOGIC — see
shared/constants/market_segments.py + docs/ml/market-segment-integration.md.
"""

from __future__ import annotations

import pytest

from shared.constants.market_segments import (
    MARKET_SEGMENT_CODE_TO_NAME,
    UNKNOWN_SEGMENT,
    is_official_code,
    is_unknown,
    resolve_market_segment,
)


# ── Every official mapping (spec §11) ────────────────────────────────────────

class TestOfficialMapping:
    @pytest.mark.parametrize(
        "code,expected",
        [
            (30, "CIB"),        # Corporate & Investment Banking
            (40, "BB"),         # Business Banking
            (45, "SME"),        # Small & Medium Enterprise
            (50, "Enterprise"), # Enterprise
            (60, "Prestige"),   # Prestige
            (65, "Personal"),   # Personal
            (75, "Mass"),       # Mass
            (85, "Premier"),    # Premier
            (90, "Staff"),      # Staff
            (99, "Internal"),   # Internal
        ],
    )
    def test_official_code_maps_to_label(self, code: int, expected: str) -> None:
        assert resolve_market_segment(code) == expected
        assert is_official_code(code) is True
        assert is_unknown(code) is False

    def test_mapping_table_matches_spec(self) -> None:
        """The authoritative table contains exactly the 10 bank codes."""
        assert MARKET_SEGMENT_CODE_TO_NAME == {
            30: "CIB",
            40: "BB",
            45: "SME",
            50: "Enterprise",
            60: "Prestige",
            65: "Personal",
            75: "Mass",
            85: "Premier",
            90: "Staff",
            99: "Internal",
        }

    def test_digit_string_codes_resolve_too(self) -> None:
        """Codes may arrive as digit strings from a VARCHAR source column."""
        assert resolve_market_segment("30") == "CIB"
        assert resolve_market_segment("45") == "SME"
        assert resolve_market_segment("99") == "Internal"


# ── Unknown / NULL / blank / non-numeric handling (spec §9, §10) ─────────────

class TestUnknownAndNullHandling:
    @pytest.mark.parametrize(
        "raw",
        [
            55,      # unknown numeric code
            12,      # unknown numeric code
            "55",    # unknown digit string
            "ABCD",  # non-numeric
            "",      # blank string
            "   ",   # whitespace
            None,    # NULL / missing
            True,    # boolean (not a code)
            45.5,    # non-integer float
        ],
    )
    def test_resolves_to_other_and_is_flagged_unknown(self, raw: object) -> None:
        assert resolve_market_segment(raw) == UNKNOWN_SEGMENT
        assert is_official_code(raw) is False
        assert is_unknown(raw) is True

    def test_unknown_value_observable_in_dq(self) -> None:
        """Unknowns must be observable, not silently dropped (spec §9)."""
        sample = [30, 45, 55, None, "", 99]
        unknown_count = sum(1 for v in sample if is_unknown(v))
        assert unknown_count == 3  # 55, None, ""
        assert unknown_count / len(sample) == 0.5  # unknown rate


# ── Code preservation (spec §3, §17) ─────────────────────────────────────────

class TestCodePreservation:
    def test_resolution_does_not_discard_source(self) -> None:
        """resolve() returns a label; callers keep the original code for lineage.

        This asserts the contract: mapping is a pure function of the code and
        the raw code is untouched by resolution (auditable source value).
        """
        raw = 45
        label = resolve_market_segment(raw)
        assert label == "SME"
        # The raw value is still available to the caller for lineage.
        assert raw == 45


# ── Normalised representation (spec §3) ──────────────────────────────────────

class TestNormalisedRepresentation:
    def test_code_and_label_pairing(self) -> None:
        """market_segment_code (45) pairs with market_segment (SME)."""
        code = 45
        assert resolve_market_segment(code) == "SME"
        assert MARKET_SEGMENT_CODE_TO_NAME[code] == "SME"
