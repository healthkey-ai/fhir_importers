"""DSTU2 Procedure handler.

Port of `legacy/.../resourcesTypes/dstu2/Procedure/index.js`. Only delta
vs r4 is the note field: DSTU2 had `notes`, r4 renamed to `note`.
"""
from __future__ import annotations

from typing import Any

from services.fhir_parsing.fhir_parsing_types import ParsedPatientPayload
from services.fhir_parsing.handlers.abstract_resource_handler import AbstractResourceHandler
from services.fhir_parsing.handlers.r4.procedure_handler import ProcedureResourceHandler


class Dstu2ProcedureResourceHandler(AbstractResourceHandler):
    def __init__(self) -> None:
        self._r4 = ProcedureResourceHandler()

    def handle(self, resource: dict[str, Any], payload: ParsedPatientPayload) -> None:
        adapted = dict(resource)
        if "notes" in resource and "note" not in resource:
            notes_raw = resource["notes"]
            if isinstance(notes_raw, str):
                adapted["note"] = [{"text": notes_raw}]
            elif isinstance(notes_raw, list):
                adapted["note"] = [
                    {"text": n} if isinstance(n, str) else n for n in notes_raw
                ]
        self._r4.handle(adapted, payload)
