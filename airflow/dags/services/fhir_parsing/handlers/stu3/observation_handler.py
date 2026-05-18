"""STU3 Observation handler.

Port of `legacy/.../resourcesTypes/stu3/Observation/index.js`. Pre-processes
the resource to rename STU3-specific fields into their r4 equivalents,
then delegates to the r4 handler. Differences from r4:
- `fhir.comment` (string)   → r4 `note` (Annotation[])
- `fhir.context`            → r4 `encounter`

`fhir.context` is currently dropped by our r4 handler (we don't model
encounters), so the rename only affects `note`. Kept for parity.
"""
from __future__ import annotations

from typing import Any

from services.fhir_parsing.fhir_parsing_types import ParsedPatientPayload
from services.fhir_parsing.handlers.abstract_resource_handler import AbstractResourceHandler
from services.fhir_parsing.handlers.r4.observation_handler import ObservationResourceHandler


class StU3ObservationResourceHandler(AbstractResourceHandler):
    def __init__(self) -> None:
        self._r4 = ObservationResourceHandler()

    def handle(self, resource: dict[str, Any], payload: ParsedPatientPayload) -> None:
        # Copy so we don't mutate the caller's resource dict.
        adapted = dict(resource)
        if "comment" in resource and "note" not in resource:
            adapted["note"] = [{"text": resource["comment"]}]
        if "context" in resource and "encounter" not in resource:
            adapted["encounter"] = resource["context"]
        self._r4.handle(adapted, payload)
