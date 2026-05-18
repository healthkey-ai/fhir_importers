"""Pre-r4 Condition.clinicalStatus / verificationStatus were plain strings.

In r4 these became CodeableConcept (with a `.coding[].code` array). STU3
and DSTU2 still use the string form. This helper normalizes either shape
to the same list-of-codes layout that `ParsedCondition.clinical_status`
expects.
"""
from __future__ import annotations

from typing import Any


def normalize_string_or_codeable_status(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw] if raw else []
    if isinstance(raw, dict):
        return [
            str(c.get("code"))
            for c in (raw.get("coding") or [])
            if isinstance(c, dict) and c.get("code") is not None
        ]
    return []
