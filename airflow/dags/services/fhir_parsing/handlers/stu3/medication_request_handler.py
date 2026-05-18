"""STU3 MedicationRequest handler.

Port of `legacy/.../resourcesTypes/stu3/MedicationRequest/index.js`. The
only structural difference vs r4 MedicationRequest is the date field:
- STU3: `dateWritten`
- r4:   `authoredOn`

The legacy STU3 normalizer also wraps a custom dosage parser that supports
`rateRange` / `rateQuantity` / `rateRatio` in dosageInstruction. Real
prescribing systems emit `doseQuantity` / `doseRange`, which our shared
parser already covers; rates are infusion-style and out of scope for the
DrugExposure mapping we produce.
"""
from __future__ import annotations

from typing import Any

from services.fhir_parsing.fhir_parsing_types import ParsedPatientPayload
from services.fhir_parsing.handlers.abstract_resource_handler import AbstractResourceHandler
from services.fhir_parsing.handlers.r4._medication_parse import parse_medication_resource


class StU3MedicationRequestResourceHandler(AbstractResourceHandler):
    def handle(self, resource: dict[str, Any], payload: ParsedPatientPayload) -> None:
        parsed = parse_medication_resource(
            resource,
            dosage_field="dosageInstruction",
            date_field="dateWritten",
            use_effective_period=False,
        )
        payload.drug_exposures.append(parsed)
