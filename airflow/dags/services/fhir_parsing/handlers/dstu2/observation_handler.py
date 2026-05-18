"""DSTU2 Observation handler.

Port of `legacy/.../resourcesTypes/dstu2/Observation/index.js`. DSTU2's
note field was `comments` (string); r4 renamed it to `note` (Annotation[]).
"""
from __future__ import annotations

from typing import Any

from services.fhir_parsing.fhir_parsing_types import ParsedPatientPayload
from services.fhir_parsing.handlers.abstract_resource_handler import AbstractResourceHandler
from services.fhir_parsing.handlers.r4.observation_handler import ObservationResourceHandler


class Dstu2ObservationResourceHandler(AbstractResourceHandler):
    def __init__(self) -> None:
        self._r4 = ObservationResourceHandler()

    def handle(self, resource: dict[str, Any], payload: ParsedPatientPayload) -> None:
        adapted = dict(resource)
        if "comments" in resource and "note" not in resource:
            adapted["note"] = [{"text": resource["comments"]}]
        self._r4.handle(adapted, payload)
