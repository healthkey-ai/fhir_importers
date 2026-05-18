"""DSTU2 MedicationOrder handler.

Port of `legacy/.../resourcesTypes/dstu2/MedicationOrder/index.js`.
MedicationOrder is the DSTU2 name for what became MedicationRequest in
STU3/r4. The resource shape is otherwise the same as STU3 MedicationRequest:
- Dosage list: `dosageInstruction[]`
- Date written: `dateWritten`
- Top-level note in DSTU2 is `note` (string), not Annotation[]; the legacy
  converts to `notes: [{text: ...}]` shape on the way out.
"""
from __future__ import annotations

from typing import Any

from services.fhir_parsing.fhir_parsing_types import ParsedPatientPayload
from services.fhir_parsing.handlers.abstract_resource_handler import AbstractResourceHandler
from services.fhir_parsing.handlers.r4._medication_parse import parse_medication_resource


class Dstu2MedicationOrderResourceHandler(AbstractResourceHandler):
    def handle(self, resource: dict[str, Any], payload: ParsedPatientPayload) -> None:
        # DSTU2's `note` is a plain string at the resource root. Wrap it so
        # the shared parser's annotation-list extraction picks it up.
        adapted = dict(resource)
        note_value = resource.get("note")
        if isinstance(note_value, str) and note_value:
            adapted["note"] = [{"text": note_value}]
        parsed = parse_medication_resource(
            adapted,
            dosage_field="dosageInstruction",
            date_field="dateWritten",
            use_effective_period=False,
        )
        payload.drug_exposures.append(parsed)
