"""Money helpers. Money is always Decimal (never float) and quantized to two places."""

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer

TWO_PLACES = Decimal("0.01")


def to_money(value: Any) -> Decimal:
    if value is None:
        raise ValueError("Money value is required")
    if isinstance(value, float):
        raise ValueError("Money must be provided as a string or integer, not a float")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid money value: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError("Money must be finite")
    return amount.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN)


def zero() -> Decimal:
    return Decimal("0.00")


Money = Annotated[
    Decimal,
    BeforeValidator(to_money),
    PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json"),
]
