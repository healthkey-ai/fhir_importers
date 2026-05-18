"""STU3 Condition handler.

Port of `legacy/.../resourcesTypes/stu3/Condition/index.js`. Differences vs r4:
- `clinicalStatus` is a plain string (not a CodeableConcept).
- `verificationStatus` is a plain string.
- `recordedDate` is named `assertedDate`.
- Category is the same shape as r4 (array of CodeableConcept).
"""
from __future__ import annotations

import logging
from typing import Any

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
from services.fhir_parsing.handlers.r4.condition_handler import (
    _extract_categories,
    _extract_stage_text,
)

_logger = logging.getLogger(__name__)


class StU3ConditionResourceHandler(AbstractResourceHandler):
    def handle(self, resource: dict[str, Any], payload: ParsedPatientPayload) -> None:
        code = resource.get("code") or {}
        parsed = ParsedCondition(
            code_text=code.get("text"),
            codings=codings_from_codeable_concept(code),
            onset_datetime=parse_datetime(resource.get("onsetDateTime")),
            recorded_date=parse_datetime(resource.get("assertedDate")),
            clinical_status=normalize_string_or_codeable_status(resource.get("clinicalStatus")),
            verification_status=normalize_string_or_codeable_status(
                resource.get("verificationStatus")
            ),
            categories=_extract_categories(resource.get("category")),
            stage_text=_extract_stage_text(resource.get("stage")),
            extension=[e for e in (resource.get("extension") or []) if isinstance(e, dict)],
        )
        if parsed.code_text is None and parsed.codings:
            parsed.code_text = parsed.codings[0].display
        payload.conditions.append(parsed)
