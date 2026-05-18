"""r4 Condition handler.

Port of `legacy/.../resourcesTypes/r4/Condition/index.js` +
`_getCategories.js` + `_getConditionMappings.js`. The legacy code resolves
SNOMED → `conditionMappings` doc in Firestore here; in our pipeline that
lookup is deferred to the writer (which can hit `ConceptRepository.find_by_code(...)`).
The handler preserves every `coding` so nothing is lost in translation.
"""
from __future__ import annotations

import logging
from typing import Any

from services.fhir_parsing.codesystems import is_fhir_administrative
from services.fhir_parsing.fhir_parsing_types import (
    ParsedCondition,
    ParsedPatientPayload,
    coding_from_dict,
    codings_from_codeable_concept,
)
from services.fhir_parsing.handlers._datetime_parse import parse_datetime
from services.fhir_parsing.handlers.abstract_resource_handler import AbstractResourceHandler

_logger = logging.getLogger(__name__)


def _extract_status_codes(codeable_concept: dict[str, Any] | None) -> list[str]:
    if not codeable_concept:
        return []
    return [
        str(c.get("code"))
        for c in (codeable_concept.get("coding") or [])
        if isinstance(c, dict) and c.get("code") is not None
    ]


def _extract_categories(category_list: list[dict[str, Any]] | None) -> list[str]:
    """Port of `_getCategories.js` — pull FHIR-administrative category codes.

    Real-world feeds emit categories with system `http://hl7.org/fhir/...`
    (or HL7 OIDs). The legacy filter keeps only those.
    """
    out: list[str] = []
    if not category_list:
        return out
    for cc in category_list:
        if not isinstance(cc, dict):
            continue
        for coding in cc.get("coding") or []:
            if isinstance(coding, dict) and is_fhir_administrative(coding) and coding.get("code"):
                out.append(str(coding["code"]))
    return out


def _extract_stage_text(stage_list: list[dict[str, Any]] | None) -> str | None:
    """Best-effort: take the first stage's `summary.text` or first coding display.

    Mirrors the Django view's stage extraction (~lines 564-574 of the legacy
    upload_fhir flow) — preserves the textual stage so PatientInfo.stage can be patched.
    """
    if not stage_list:
        return None
    summary = (stage_list[0] or {}).get("summary") or {}
    if summary.get("text"):
        return str(summary["text"])
    coding_list = summary.get("coding") or []
    if coding_list:
        display = (coding_list[0] or {}).get("display")
        if display:
            return str(display)
    return None


class ConditionResourceHandler(AbstractResourceHandler):
    def handle(self, resource: dict[str, Any], payload: ParsedPatientPayload) -> None:
        code = resource.get("code") or {}
        parsed = ParsedCondition(
            code_text=code.get("text"),
            codings=codings_from_codeable_concept(code),
            onset_datetime=parse_datetime(resource.get("onsetDateTime")),
            recorded_date=parse_datetime(resource.get("recordedDate")),
            clinical_status=_extract_status_codes(resource.get("clinicalStatus")),
            verification_status=_extract_status_codes(resource.get("verificationStatus")),
            categories=_extract_categories(resource.get("category")),
            stage_text=_extract_stage_text(resource.get("stage")),
            extension=[
                e for e in (resource.get("extension") or []) if isinstance(e, dict)
            ],
        )

        if parsed.code_text is None and parsed.codings:
            parsed.code_text = parsed.codings[0].display

        payload.conditions.append(parsed)
