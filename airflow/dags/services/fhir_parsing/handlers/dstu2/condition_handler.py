"""DSTU2 Condition handler.

Port of `legacy/.../resourcesTypes/dstu2/Condition/index.js`. Differences
vs r4:
- `clinicalStatus` and `verificationStatus` are plain strings.
- `recordedDate` is named `dateRecorded`.
- `category` is a SINGLE CodeableConcept (not an array).
"""
from __future__ import annotations

import logging
from typing import Any

from services.fhir_parsing.codesystems import is_fhir_administrative
from services.fhir_parsing.fhir_parsing_types import (
    ParsedCondition,
    ParsedPatientPayload,
    codings_from_codeable_concept,
)
from services.fhir_parsing.handlers._datetime_parse import parse_datetime
from services.fhir_parsing.handlers._legacy_condition_status import (
    normalize_string_or_codeable_status,
)
from services.fhir_parsing.handlers.abstract_resource_handler import AbstractResourceHandler
from services.fhir_parsing.handlers.r4.condition_handler import _extract_stage_text

_logger = logging.getLogger(__name__)


def _extract_category_singular(category: dict[str, Any] | None) -> list[str]:
    """DSTU2 `category` is a single CodeableConcept rather than an array."""
    if not isinstance(category, dict):
        return []
    return [
        str(c["code"])
        for c in category.get("coding") or []
        if isinstance(c, dict) and is_fhir_administrative(c) and c.get("code")
    ]


class Dstu2ConditionResourceHandler(AbstractResourceHandler):
    def handle(self, resource: dict[str, Any], payload: ParsedPatientPayload) -> None:
        code = resource.get("code") or {}
        parsed = ParsedCondition(
            code_text=code.get("text"),
            codings=codings_from_codeable_concept(code),
            onset_datetime=parse_datetime(resource.get("onsetDateTime")),
            recorded_date=parse_datetime(resource.get("dateRecorded")),
            clinical_status=normalize_string_or_codeable_status(resource.get("clinicalStatus")),
            verification_status=normalize_string_or_codeable_status(
                resource.get("verificationStatus")
            ),
            categories=_extract_category_singular(resource.get("category")),
            stage_text=_extract_stage_text(resource.get("stage")),
            extension=[e for e in (resource.get("extension") or []) if isinstance(e, dict)],
        )
        if parsed.code_text is None and parsed.codings:
            parsed.code_text = parsed.codings[0].display
        payload.conditions.append(parsed)
