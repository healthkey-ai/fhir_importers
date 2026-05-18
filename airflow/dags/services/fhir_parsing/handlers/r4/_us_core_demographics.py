"""US Core race / ethnicity extension parser.

Ported from `legacy/.../FHIR/utils/usCoreDemographics.js`. Self-contained —
no DB or Firestore dependency.
"""
from __future__ import annotations

from typing import Any

from services.fhir_parsing.fhir_parsing_types import Coding, RaceExtension, coding_from_dict

US_CORE_RACE_URL = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-race"
US_CORE_ETHNICITY_URL = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity"

# Top-level OMB race categories. Anything else falls back to "Other".
RACE_CANONICAL_MAP: dict[str, str] = {
    "1002-5": "American Indian or Alaska Native",
    "2028-9": "Asian",
    "2054-5": "Black or African American",
    "2076-8": "Native Hawaiian or Other Pacific Islander",
    "2106-3": "White",
    "2131-1": "Other",
}

# OMB ethnicity categories per US Core.
ETHNICITY_CANONICAL_MAP: dict[str, str] = {
    "2135-2": "Hispanic or Latino",
    "2186-5": "Not Hispanic or Latino",
}


def _collect_codings_by_url(extension: dict[str, Any], target_url: str) -> list[Coding]:
    seen: set[tuple[str, str, str]] = set()
    out: list[Coding] = []
    for inner in extension.get("extension") or []:
        if inner.get("url") != target_url:
            continue
        value = inner.get("valueCoding")
        if not value:
            continue
        coded = coding_from_dict(value)
        if coded is None:
            continue
        key = (coded.code or "", coded.display or "", coded.system or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(coded)
    return out


def _collect_text_by_url(extension: dict[str, Any], target_url: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for inner in extension.get("extension") or []:
        if inner.get("url") != target_url:
            continue
        text = (inner.get("valueString") or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _map_codings_to_canonical(
    codings: list[Coding],
    canonical_map: dict[str, str],
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for coded in codings:
        if not coded.code:
            continue
        mapped = canonical_map.get(coded.code)
        if mapped and mapped not in seen:
            seen.add(mapped)
            out.append(mapped)
    return out


def _extract_us_core_demographics(
    fhir: dict[str, Any],
    extension_url: str,
    canonical_map: dict[str, str],
    fallback: str | None,
) -> RaceExtension | None:
    extensions = fhir.get("extension") or []
    if not isinstance(extensions, list):
        return None
    matching = next(
        (ext for ext in extensions if isinstance(ext, dict) and ext.get("url") == extension_url),
        None,
    )
    if not matching:
        return None

    omb_codings = _collect_codings_by_url(matching, "ombCategory")
    detailed = _collect_codings_by_url(matching, "detailed")
    text_values = _collect_text_by_url(matching, "text")

    canonical = _map_codings_to_canonical(omb_codings, canonical_map)
    if not canonical and fallback and (omb_codings or detailed or text_values):
        canonical = [fallback]

    if not canonical and not omb_codings and not detailed and not text_values:
        return None

    return RaceExtension(
        canonical=canonical,
        omb_categories=omb_codings,
        detailed=detailed,
        text_values=text_values,
    )


def extract_race(fhir: dict[str, Any]) -> RaceExtension | None:
    return _extract_us_core_demographics(fhir, US_CORE_RACE_URL, RACE_CANONICAL_MAP, "Other")


def extract_ethnicity(fhir: dict[str, Any]) -> RaceExtension | None:
    return _extract_us_core_demographics(
        fhir, US_CORE_ETHNICITY_URL, ETHNICITY_CANONICAL_MAP, None
    )
