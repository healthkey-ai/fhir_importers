"""Shared parser for the three medication-history-style FHIR resources.

- `MedicationStatement` (r4)       — dosage field is `dosage[]`, date is `dateAsserted` (+ `effectivePeriod`).
- `MedicationRequest`  (r4 / stu3) — dosage field is `dosageInstruction[]`, date is `authoredOn` (stu3: `dateWritten`).
- `MedicationOrder`    (dstu2)     — dosage field is `dosageInstruction[]`, date is `dateWritten`.

The bodies are otherwise identical: same `medicationCodeableConcept` /
`medicationReference` resolution, same dosage parser, same notes/status
extraction. Centralised here so the per-version handlers stay thin.
"""
from __future__ import annotations

import logging
from typing import Any

from services.fhir_parsing.codesystems import rxnorm_from_codings
from services.fhir_parsing.fhir_parsing_types import (
    Coding,
    ParsedDrugExposure,
    codings_from_codeable_concept,
)
from services.fhir_parsing.handlers._datetime_parse import parse_datetime
from services.fhir_parsing.handlers.r4._dosage_parse import parse_dosage_entry

_logger = logging.getLogger(__name__)


def _medication_text_and_codings(resource: dict[str, Any]) -> tuple[str | None, list[Coding]]:
    cc = resource.get("medicationCodeableConcept")
    if cc:
        codings = codings_from_codeable_concept(cc)
        text = cc.get("text") or next((c.display for c in codings if c.display), None)
        return text, codings
    ref = resource.get("medicationReference") or {}
    if ref.get("display"):
        return ref["display"], []
    return None, []


def _extract_status_reason_text(raw: Any) -> str | None:
    if not raw:
        return None
    entries = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("text"):
            return str(entry["text"])
        for coding in entry.get("coding") or []:
            if isinstance(coding, dict) and coding.get("display"):
                return str(coding["display"])
    return None


def _extract_notes(raw: Any) -> list[str]:
    """FHIR Annotation[] → list of strings. Each Annotation has `.text`."""
    out: list[str] = []
    if not raw:
        return out
    entries = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("text"):
            out.append(str(entry["text"]))
        elif isinstance(entry, str):
            out.append(entry)
    return out


def parse_medication_resource(
    resource: dict[str, Any],
    *,
    dosage_field: str,
    date_field: str | None,
    use_effective_period: bool,
) -> ParsedDrugExposure:
    """Convert any of MedicationStatement / MedicationRequest / MedicationOrder
    into a `ParsedDrugExposure`. Per-version differences supplied via
    keyword args.

    Args:
        dosage_field: 'dosage' (MedicationStatement) or 'dosageInstruction'
            (MedicationRequest, MedicationOrder).
        date_field: 'dateAsserted' / 'authoredOn' / 'dateWritten'.
            None if the resource carries no such top-level scalar date.
        use_effective_period: MedicationStatement carries `effectivePeriod`;
            MedicationRequest/MedicationOrder do not.
    """
    medication_text, codings = _medication_text_and_codings(resource)
    rxnorm_codes = rxnorm_from_codings([c.model_dump() for c in codings])
    notes = _extract_notes(resource.get("note"))

    effective_period = (
        resource.get("effectivePeriod") if use_effective_period else None
    ) or {}

    authored_on = parse_datetime(resource.get(date_field)) if date_field else None

    parsed = ParsedDrugExposure(
        medication_text=medication_text,
        medication_codings=codings,
        rxnorm_codes=rxnorm_codes,
        status=resource.get("status"),
        status_reason_text=_extract_status_reason_text(resource.get("statusReason")),
        effective_datetime=parse_datetime(resource.get("effectiveDateTime")),
        effective_period_start=parse_datetime(effective_period.get("start")),
        effective_period_end=parse_datetime(effective_period.get("end")),
        authored_on=authored_on,
        notes=notes,
    )

    for dosage in resource.get(dosage_field) or []:
        if isinstance(dosage, dict):
            parsed.dosages.append(parse_dosage_entry(dosage))

    return parsed
