"""r4 Procedure handler.

Port of `legacy/.../resourcesTypes/r4/Procedure/getNormalization.js` +
`_getProcedureMappings.js`. CPT→SNOMED cross-mapping happens here so the
writer can resolve `concept_id` via SNOMED first (no Firestore lookup needed).
"""
from __future__ import annotations

import logging
from typing import Any

from services.fhir_parsing.codesystems import cpt_to_snomed, is_cpt, is_snomed
from services.fhir_parsing.fhir_parsing_types import (
    ParsedPatientPayload,
    ParsedProcedure,
    codings_from_codeable_concept,
)
from services.fhir_parsing.handlers._datetime_parse import parse_datetime
from services.fhir_parsing.handlers.abstract_resource_handler import AbstractResourceHandler

_logger = logging.getLogger(__name__)


def _snomed_from_codings(codings: list[Any]) -> str | None:
    """Pick a SNOMED code directly, or convert the first CPT entry via cross-map."""
    for coded in codings:
        coding_dict = {"system": coded.system, "code": coded.code}
        if is_snomed(coding_dict) and coded.code:
            return str(coded.code)
    for coded in codings:
        coding_dict = {"system": coded.system, "code": coded.code}
        if is_cpt(coding_dict):
            mapped = cpt_to_snomed(coded.code)
            if mapped:
                return mapped
    return None


class ProcedureResourceHandler(AbstractResourceHandler):
    def handle(self, resource: dict[str, Any], payload: ParsedPatientPayload) -> None:
        code = resource.get("code") or {}
        period = resource.get("performedPeriod") or {}
        codings = codings_from_codeable_concept(code)

        notes: list[str] = []
        for entry in resource.get("note") or []:
            if isinstance(entry, dict) and entry.get("text"):
                notes.append(str(entry["text"]))

        parsed = ParsedProcedure(
            codings=codings,
            code_text=code.get("text") or (codings[0].display if codings else None),
            snomed_code_from_cpt=_snomed_from_codings(codings),
            status=resource.get("status"),
            performed_datetime=parse_datetime(resource.get("performedDateTime")),
            performed_period_start=parse_datetime(period.get("start")),
            performed_period_end=parse_datetime(period.get("end")),
            notes=notes,
        )

        payload.procedures.append(parsed)
