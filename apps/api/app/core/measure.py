"""Measurement policy: originals are stored exactly as entered; conversions are explicit, derived values.

Only units with a fixed legal definition are converted. Regional units whose size varies by
state or district (bigha, biswa, kattha, ...) are never auto-converted.
"""

from decimal import Decimal

AREA_TO_SQM: dict[str, Decimal] = {
    "sqm": Decimal("1"),
    "sqft": Decimal("0.09290304"),
    "sqyd": Decimal("0.83612736"),
    "acre": Decimal("4046.8564224"),
    "hectare": Decimal("10000"),
    "are": Decimal("100"),
    "guntha": Decimal("101.17141056"),
    "cent": Decimal("40.468564224"),
}

LENGTH_TO_M: dict[str, Decimal] = {
    "m": Decimal("1"),
    "ft": Decimal("0.3048"),
    "yd": Decimal("0.9144"),
    "km": Decimal("1000"),
}

AREA_UNITS = sorted(AREA_TO_SQM) + ["bigha", "biswa", "kanal", "marla", "kattha", "ground"]
LENGTH_UNITS = sorted(LENGTH_TO_M)


def derive_area_sqm(value: Decimal | None, unit: str | None) -> dict | None:
    if value is None or not unit:
        return None
    factor = AREA_TO_SQM.get(unit.lower())
    if factor is None:
        return None
    return {
        "value": format((Decimal(value) * factor).quantize(Decimal("0.0001")), "f"),
        "unit": "sqm",
        "derived": True,
        "formula": f"value * {factor} ({unit} -> sqm)",
        "sources": {"value": format(Decimal(value), "f"), "unit": unit},
    }


def derive_length_m(value: Decimal | None, unit: str | None) -> dict | None:
    if value is None or not unit:
        return None
    factor = LENGTH_TO_M.get(unit.lower())
    if factor is None:
        return None
    return {
        "value": format((Decimal(value) * factor).quantize(Decimal("0.0001")), "f"),
        "unit": "m",
        "derived": True,
        "formula": f"value * {factor} ({unit} -> m)",
        "sources": {"value": format(Decimal(value), "f"), "unit": unit},
    }


def derived_decimal(derived: dict | None) -> Decimal | None:
    return Decimal(derived["value"]) if derived else None
