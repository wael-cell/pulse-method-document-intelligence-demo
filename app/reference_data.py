"""
Reference material catalog (the "source of truth" the validator checks against).

In a real deployment this would be a managed table in Postgres, an ERP/MRP
export, or a client-provided master list. For the demo it is an in-memory
catalog with a small, realistic lookup API so the validation layer has something
deterministic to validate against.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MaterialRecord:
    """One canonical material in the reference catalog."""

    code: str
    canonical_name: str
    category: str
    default_unit: str
    allowed_units: frozenset[str]
    spec_standard: str | None = None
    # Sanity bounds used to catch obviously-wrong extracted quantities.
    min_quantity: float = 0.0
    max_quantity: float = 1_000_000.0


# --------------------------------------------------------------------------------------
# Catalog (construction / operations flavored, but domain-agnostic in structure)
# --------------------------------------------------------------------------------------
_CATALOG: dict[str, MaterialRecord] = {
    rec.code: rec
    for rec in [
        MaterialRecord(
            code="CMU-8",
            canonical_name='Concrete Masonry Unit, 8" standard',
            category="masonry",
            default_unit="EA",
            allowed_units=frozenset({"EA", "PCS"}),
            spec_standard="ASTM C90",
            max_quantity=200_000,
        ),
        MaterialRecord(
            code="CONC-4000",
            canonical_name="Ready-Mix Concrete, 4000 psi",
            category="concrete",
            default_unit="CY",
            allowed_units=frozenset({"CY", "CUYD"}),
            spec_standard="ASTM C94",
            max_quantity=50_000,
        ),
        MaterialRecord(
            code="RB-#5",
            canonical_name="Reinforcing Bar #5 (16 mm)",
            category="reinforcement",
            default_unit="LF",
            allowed_units=frozenset({"LF", "FT", "TON"}),
            spec_standard="ASTM A615",
            max_quantity=500_000,
        ),
        MaterialRecord(
            code="STL-W12X26",
            canonical_name="Structural Steel Wide-Flange W12x26",
            category="structural_steel",
            default_unit="LF",
            allowed_units=frozenset({"LF", "FT"}),
            spec_standard="ASTM A992",
            max_quantity=100_000,
        ),
        MaterialRecord(
            code="GYP-58",
            canonical_name='Gypsum Board 5/8" Type X',
            category="finishes",
            default_unit="SF",
            allowed_units=frozenset({"SF", "SHT"}),
            spec_standard="ASTM C1396",
            max_quantity=500_000,
        ),
        MaterialRecord(
            code="INS-R19",
            canonical_name="Batt Insulation R-19",
            category="thermal",
            default_unit="SF",
            allowed_units=frozenset({"SF"}),
            spec_standard="ASTM C665",
            max_quantity=500_000,
        ),
        MaterialRecord(
            code="PVC-4",
            canonical_name='PVC Pipe 4" Schedule 40',
            category="plumbing",
            default_unit="LF",
            allowed_units=frozenset({"LF", "FT"}),
            spec_standard="ASTM D1785",
            max_quantity=100_000,
        ),
        MaterialRecord(
            code="EMT-34",
            canonical_name='Electrical Metallic Tubing 3/4"',
            category="electrical",
            default_unit="LF",
            allowed_units=frozenset({"LF", "FT"}),
            spec_standard="UL 797",
            max_quantity=100_000,
        ),
    ]
}

# Alias table: common messy spellings/variants the extractor may emit, mapped to
# the canonical code. This is what lets the validator "recognize" sloppy input.
_ALIASES: dict[str, str] = {
    "CMU8": "CMU-8",
    "CMU-08": "CMU-8",
    "8IN CMU": "CMU-8",
    "RB#5": "RB-#5",
    "REBAR#5": "RB-#5",
    "#5 REBAR": "RB-#5",
    "W12X26": "STL-W12X26",
    "W12-26": "STL-W12X26",
    "GYP58": "GYP-58",
    "5/8 GYP": "GYP-58",
    "R-19": "INS-R19",
    "R19": "INS-R19",
    "PVC4": "PVC-4",
    'PVC 4"': "PVC-4",
    "EMT34": "EMT-34",
}


def _normalize(code: str) -> str:
    return code.strip().upper().replace("  ", " ")


def resolve_code(code: str | None) -> MaterialRecord | None:
    """Resolve a (possibly messy) code to a canonical catalog record, or None."""
    if not code:
        return None
    key = _normalize(code)
    if key in _CATALOG:
        return _CATALOG[key]
    alias_target = _ALIASES.get(key)
    if alias_target:
        return _CATALOG[alias_target]
    return None


def all_codes() -> list[str]:
    """Return all canonical catalog codes (handy for tests and tooling)."""
    return sorted(_CATALOG.keys())


def catalog_size() -> int:
    return len(_CATALOG)
