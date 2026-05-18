"""r4 MedicationStatement handler.

Adapted from `legacy/.../resourcesTypes/r4/MedicationRequest/getNormalization.js`.
FHIR's two medication-history resources have nearly identical content shapes;
the only structural difference is `MedicationStatement.dosage[]` vs
`MedicationRequest.dosageInstruction[]`, and `effectivePeriod`/`effectiveDateTime`
on Statement vs `authoredOn` + `dispenseRequest.validityPeriod` on Request.
"""
from __future__ import annotations

import logging
from typing import Any

from services.fhir_parsing.codesystems import rxnorm_from_codings
from services.fhir_parsing.fhir_parsing_types import (
    Coding,
    ParsedDrugExposure,
    ParsedPatientPayload,
    codings_from_codeable_concept,
)
from services.fhir_parsing.handlers._datetime_parse import parse_datetime
from services.fhir_parsing.handlers.abstract_resource_handler import AbstractResourceHandler
from services.fhir_parsing.handlers.r4._dosage_parse import parse_dosage_entry

_logger = logging.getLogger(__name__)


def _medication_text_and_codings(resource: dict[str, Any]) -> tuple[str | None, list[Coding]]:
    """Resolve `medicationCodeableConcept` or `medicationReference.display`.

    The legacy code, on a `medicationReference` miss, would chase the
    referenced `Medication` resource in Firestore. In a Bundle context that
    `Medication` is usually in the same bundle, but per-patient lookup of
    contained resources is left out of scope here — the writer can resolve
    via `concept_id` from the `medicationCodeableConcept.coding` when present.
    """
    cc = resource.get("medicationCodeableConcept")
    if cc:
        codings = codings_from_codeable_concept(cc)
        text = cc.get("text") or next(
            (c.display for c in codings if c.display),
            None,
        )
        return text, codings

    ref = resource.get("medicationReference") or {}
    if ref.get("display"):
        return ref["display"], []
    return None, []


def _coalesce_dict_as_dict(raw: Any) -> dict[str, Any]:
    return raw if isinstance(raw, dict) else {}


class MedicationStatementResourceHandler(AbstractResourceHandler):
    def handle(self, resource: dict[str, Any], payload: ParsedPatientPayload) -> None:
        medication_text, codings = _medication_text_and_codings(resource)
        rxnorm_codes = rxnorm_from_codings([c.model_dump() for c in codings])

        # FHIR allows `Annotation[]` for notes — text lives under `.text`.
        notes: list[str] = []
        for entry in resource.get("note") or []:
            if isinstance(entry, dict) and entry.get("text"):
                notes.append(str(entry["text"]))

        effective_period = _coalesce_dict_as_dict(resource.get("effectivePeriod"))

        parsed = ParsedDrugExposure(
            medication_text=medication_text,
            medication_codings=codings,
            rxnorm_codes=rxnorm_codes,
            status=resource.get("status"),
            status_reason_text=_extract_status_reason(resource.get("statusReason")),
            effective_datetime=parse_datetime(resource.get("effectiveDateTime")),
            effective_period_start=parse_datetime(effective_period.get("start")),
            effective_period_end=parse_datetime(effective_period.get("end")),
            authored_on=parse_datetime(resource.get("dateAsserted")),
            notes=notes,
        )

        for dosage in resource.get("dosage") or []:
            if isinstance(dosage, dict):
                parsed.dosages.append(parse_dosage_entry(dosage))

        payload.drug_exposures.append(parsed)


def _extract_status_reason(raw: Any) -> str | None:
    if not raw:
        return None
    if isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict):
        entries = [raw]
    else:
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("text"):
            return str(entry["text"])
        for coding in entry.get("coding") or []:
            if isinstance(coding, dict) and coding.get("display"):
                return str(coding["display"])
    return None
