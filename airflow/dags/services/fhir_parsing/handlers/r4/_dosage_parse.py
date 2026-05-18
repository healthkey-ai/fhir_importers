"""Dosage instruction parser shared by MedicationRequest and MedicationStatement.

Port of `createDoses` + `getDoseSummary` from
`legacy/.../resourcesTypes/r4/MedicationRequest/getNormalization.js`.

The FHIR shape is nearly identical between the two resources:
- `MedicationRequest.dosageInstruction[]` → `Dosage`
- `MedicationStatement.dosage[]`          → `Dosage`

Each `Dosage` carries `doseAndRate[]` with one of:
- `doseQuantity { value, unit }`         → type=QUANTITY
- `doseRange    { low, high }`           → type=RANGE
- `rateQuantity` / `rateRange`           → (not used by legacy summary)

The legacy code prefers `doseAndRate[].type` in {`calculated`, `ordered`},
falling back to `ordered` alone. We mirror that priority.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Iterable

from services.fhir_parsing.fhir_parsing_types import ParsedDosage, ParsedDose
from services.fhir_parsing.handlers._datetime_parse import parse_datetime

_logger = logging.getLogger(__name__)


def _type_matches(dose_rate: dict[str, Any], wanted: Iterable[str]) -> bool:
    type_section = dose_rate.get("type") or {}
    if isinstance(type_section, dict):
        if type_section.get("text") in wanted:
            return True
        for coding in type_section.get("coding") or []:
            if isinstance(coding, dict) and coding.get("code") in wanted:
                return True
    return False


def _pick_dose_and_rate(
    dose_and_rate: list[dict[str, Any]] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (target_amount, ordered_fallback).

    The legacy logic prefers a row typed as 'calculated' or 'ordered'; if
    neither is tagged, it falls through and the caller treats the chosen row
    as a calculated/ordered union.
    """
    if not dose_and_rate:
        return None, None
    target: dict[str, Any] | None = None
    ordered: dict[str, Any] | None = None
    for entry in dose_and_rate:
        if not isinstance(entry, dict):
            continue
        if target is None and _type_matches(entry, ("calculated", "ordered")):
            target = entry
        if ordered is None and _type_matches(entry, ("ordered",)):
            ordered = entry
    return target, ordered


def _build_dose_from_amount(amount: dict[str, Any]) -> ParsedDose | None:
    """Extract a `ParsedDose` from a single doseAndRate entry."""
    if not amount:
        return None
    if amount.get("doseRange"):
        dr = amount["doseRange"]
        high = dr.get("high") or {}
        return ParsedDose(
            type="RANGE",
            value={"low": dr.get("low"), "high": dr.get("high")},
            unit=high.get("unit"),
        )
    if amount.get("doseQuantity"):
        dq = amount["doseQuantity"]
        return ParsedDose(
            type="QUANTITY",
            value=dq.get("value"),
            unit=dq.get("unit"),
        )
    return None


def _apply_timing_repeat(dose: ParsedDose, dosage_repeat: dict[str, Any]) -> None:
    """Mutate `dose` with bounds / frequency / period from `timing.repeat`."""
    if not dosage_repeat:
        return
    for bounds_key in ("boundsPeriod", "boundsRange", "boundsQuantity"):
        bounds = dosage_repeat.get(bounds_key)
        if not isinstance(bounds, dict):
            continue
        if "start" in bounds:
            dose.start = parse_datetime(bounds["start"])
        if "end" in bounds:
            dose.end = parse_datetime(bounds["end"])
        # boundsRange uses low/high; legacy includes them but we don't model
        # range-bounded dosing separately.
    dose.frequency = dosage_repeat.get("frequency")
    period = dosage_repeat.get("period")
    if isinstance(period, (int, float)):
        dose.period = float(period)
    dose.period_unit = dosage_repeat.get("periodUnit")


def _format_summary(dose: ParsedDose) -> str | None:
    """Port of `getDoseSummary`. Builds the human-readable dose blurb."""
    parts: list[str] = []
    if dose.text:
        parts.append(str(dose.text))
    else:
        if dose.type == "RANGE" and isinstance(dose.value, dict):
            low = (dose.value.get("low") or {}).get("value")
            high = (dose.value.get("high") or {}).get("value")
            unit = dose.unit or ""
            if low is not None and high is not None:
                parts.append(f"{low} {unit} - {high} {unit}".strip())
        elif dose.value is not None and dose.type == "QUANTITY":
            unit = dose.unit or ""
            parts.append(f"{dose.value} {unit}".strip())

        if dose.frequency and dose.period is not None:
            if dose.period > 1:
                parts.append(
                    f"{dose.frequency} dose/{dose.period} {dose.period_unit or ''}".strip()
                )
            else:
                parts.append(f"{dose.frequency} dose/{dose.period_unit or ''}".strip())

    if dose.start and dose.end:
        start_str = dose.start.strftime("%b %d, %Y")
        end_str = dose.end.strftime("%b %d, %Y")
        if (dose.end - dose.start).days > 0:
            parts.append(f"from {start_str} to {end_str}")
        else:
            parts.append(f"on {start_str}")

    summary = " ".join(p for p in parts if p)
    return summary or None


def parse_dosage_entry(dosage: dict[str, Any]) -> ParsedDosage:
    """Parse a single FHIR Dosage entry into a `ParsedDosage`."""
    target, ordered = _pick_dose_and_rate(dosage.get("doseAndRate"))
    chosen = target or ordered
    dose = _build_dose_from_amount(chosen) if chosen else ParsedDose()

    if dose is None:
        dose = ParsedDose()

    timing = dosage.get("timing") or {}
    repeat = timing.get("repeat")
    if isinstance(repeat, dict):
        _apply_timing_repeat(dose, repeat)

    dose.text = " , ".join(
        part for part in (dosage.get("text"), (timing.get("code") or {}).get("text")) if part
    ) or None
    dose.summary = _format_summary(dose)

    route = dosage.get("route") or {}
    route_text = route.get("text")
    if not route_text:
        coding_displays = [
            c.get("display") for c in route.get("coding") or [] if isinstance(c, dict)
        ]
        coding_displays = [d for d in coding_displays if d]
        route_text = ", ".join(coding_displays) if coding_displays else None

    return ParsedDosage(
        label=dosage.get("text")
        or (dosage.get("code") or {}).get("text")
        or dosage.get("patientInstruction"),
        route=route_text,
        dose=dose,
    )
