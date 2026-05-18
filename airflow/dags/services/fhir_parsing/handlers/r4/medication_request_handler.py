"""r4 MedicationRequest handler.

MedicationRequest is FHIR's prescription/order resource — same content as
MedicationStatement at the level we care about, but the dosage field is
`dosageInstruction[]` and the date field is `authoredOn`.
"""
from __future__ import annotations

from typing import Any

from services.fhir_parsing.fhir_parsing_types import ParsedPatientPayload
from services.fhir_parsing.handlers.abstract_resource_handler import AbstractResourceHandler
from services.fhir_parsing.handlers.r4._medication_parse import parse_medication_resource


class MedicationRequestResourceHandler(AbstractResourceHandler):
    def handle(self, resource: dict[str, Any], payload: ParsedPatientPayload) -> None:
        parsed = parse_medication_resource(
            resource,
            dosage_field="dosageInstruction",
            date_field="authoredOn",
            use_effective_period=False,
        )
        payload.drug_exposures.append(parsed)
