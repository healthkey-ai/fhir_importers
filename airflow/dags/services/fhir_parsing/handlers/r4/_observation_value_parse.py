"""Observation `value[x]` parsers — direct ports of the legacy bits.

Two operations live here:
- `convert_value_string_to_value_quantity` (port of
  `legacy/.../resourcesTypes/r4/Observation/convertValueStringToValueQuantity.js`):
  rescue heuristic that turns strings like `">5.0 mg/dL"` into a `valueQuantity`
  plus the symbol that was stripped. Lab feeds sometimes encode lower-of-detection
  inequalities this way.
- `parse_value_quantity_dict`: trivial dict-to-Pydantic for the FHIR Quantity type.
"""
from __future__ import annotations

import logging
from typing import Any

from services.fhir_parsing.fhir_parsing_types import (
    ParsedRange,
    ParsedRatio,
    ParsedValueQuantity,
)

_logger = logging.getLogger(__name__)

_ALLOWED_INEQUALITY_SYMBOLS = ("<=", ">=", "<", ">")
_AMOUNT_TO_ADD_SUBTRACT = 0.0001


def _coerce_float(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def parse_value_quantity_dict(raw: dict[str, Any] | None) -> ParsedValueQuantity | None:
    if not raw:
        return None
    value = _coerce_float(raw.get("value"))
    if value is None and raw.get("value") is not None:
        # Legacy `convertLoincValueQuantity.js` accepts `.5` style numbers.
        text = str(raw["value"])
        if text.startswith("."):
            value = _coerce_float("0" + text)
    return ParsedValueQuantity(
        value=value,
        unit=raw.get("unit"),
        code=raw.get("code"),
        system=raw.get("system"),
        comparator=raw.get("comparator"),
    )


def parse_value_range_dict(raw: dict[str, Any] | None) -> ParsedRange | None:
    if not raw:
        return None
    return ParsedRange(
        low=parse_value_quantity_dict(raw.get("low")),
        high=parse_value_quantity_dict(raw.get("high")),
    )


def parse_value_ratio_dict(raw: dict[str, Any] | None) -> ParsedRatio | None:
    if not raw:
        return None
    return ParsedRatio(
        numerator=parse_value_quantity_dict(raw.get("numerator")),
        denominator=parse_value_quantity_dict(raw.get("denominator")),
    )


def convert_value_string_to_value_quantity(
    value_string: str,
) -> tuple[ParsedValueQuantity | None, str | None]:
    """Port of `convertValueStringToValueQuantity.js`.

    Returns (quantity, symbol) on success; (None, None) when the string
    doesn't match the `"<num> <unit>"` pattern with a recognized comparator.

    The legacy code nudges the value by 0.0001 for `<`/`>` so downstream
    range checks treat the threshold as exclusive. We replicate the nudge.
    """
    if not value_string:
        return None, None
    parts = value_string.split(" ")
    if len(parts) != 2:
        return None, None
    inequality, unit = parts

    symbol_found: str | None = None
    symbol_index = -1
    for symbol in _ALLOWED_INEQUALITY_SYMBOLS:
        idx = inequality.find(symbol)
        if idx != -1:
            symbol_found = symbol
            symbol_index = idx
            break
    if symbol_found is None:
        return None, None

    numeric = inequality[symbol_index + len(symbol_found):]
    decimal = _coerce_float(numeric)
    if decimal is None:
        return None, None

    if symbol_found == ">":
        decimal += _AMOUNT_TO_ADD_SUBTRACT
    elif symbol_found == "<":
        decimal -= _AMOUNT_TO_ADD_SUBTRACT
    return ParsedValueQuantity(value=decimal, unit=unit), symbol_found
