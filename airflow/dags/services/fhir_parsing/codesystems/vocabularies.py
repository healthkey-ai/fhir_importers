"""FHIR `coding.system` URL pattern → vocabulary detection.

Ported from `legacy/.../FHIR/codeSystems/is{Loinc,Snomed,ICD10,ICD9,CPT,RxNorm,Healthtree,FHIR}.js`.

The legacy detectors use lax substring matches because real FHIR feeds from
EHR vendors emit a wild variety of system URLs for the same vocabulary
(OID form, HL7 URL form, vendor-specific form). Match the JS heuristics
verbatim so an unfamiliar EHR doesn't go unrecognized.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any


class Vocabulary(StrEnum):
    """OMOP-aligned vocabulary ids used by `concept.vocabulary_id`."""

    LOINC = "LOINC"
    SNOMED = "SNOMED"
    ICD10 = "ICD10"
    ICD9 = "ICD9"
    CPT4 = "CPT4"
    RXNORM = "RxNorm"
    HEALTHTREE = "Healthtree"
    FHIR_ADMINISTRATIVE = "FHIR_ADMINISTRATIVE"


def _system(coding: dict[str, Any] | None) -> str:
    return ((coding or {}).get("system") or "")


def _system_lower(coding: dict[str, Any] | None) -> str:
    return _system(coding).lower()


def is_loinc(coding: dict[str, Any] | None) -> bool:
    s = _system(coding)
    return (
        "loinc" in s.lower()
        or s == "urn:oid:2.16.840.1.113883.6.1"
        or s == "2.16.840.1.113883.6.1"
    )


def is_snomed(coding: dict[str, Any] | None) -> bool:
    s = _system(coding)
    return (
        "snomed" in s.lower()
        or s == "urn:oid:2.16.840.1.113883.6.96"
        or s == "2.16.840.1.113883.6.96"
    )


def is_icd10(coding: dict[str, Any] | None) -> bool:
    s = _system_lower(coding)
    return (
        s == "http://hl7.org/fhir/sid/icd-10"
        or "icd10" in s
        or "2.16.840.1.113883.6.3" in s     # ICD-10
        or "2.16.840.1.113883.6.90" in s    # ICD-10-CM (US)
    )


def is_icd9(coding: dict[str, Any] | None) -> bool:
    s = _system_lower(coding)
    return (
        s == "http://hl7.org/fhir/sid/icd-9"
        or "icd0" in s
        or "2.16.840.1.113883.6.42" in s
    )


def is_cpt(coding: dict[str, Any] | None) -> bool:
    s = _system_lower(coding)
    return (
        "2.16.840.1.113883.6.12" in s
        or "cpt" in s
        or s == "http://www.ama-assn.org/go/cpt"
    )


def is_rxnorm(coding: dict[str, Any] | None) -> bool:
    s = _system_lower(coding)
    return (
        "rxnorm" in s
        or s == "urn:oid:2.16.840.1.113883.6.88"
        or s == "2.16.840.1.113883.6.88"
    )


def is_healthtree(coding: dict[str, Any] | None) -> bool:
    return "healthtree.org" in _system(coding)


def is_fhir_administrative(coding: dict[str, Any] | None) -> bool:
    """FHIR-internal administrative code systems (e.g. condition categories)."""
    s = _system(coding)
    return (
        "hl7.org" in s
        or s == "urn:oid:2.16.840.1.113883.6.209"
        or s == "2.16.840.1.113883.6.209"
    )


_DETECTORS: tuple[tuple[Vocabulary, callable], ...] = (
    (Vocabulary.LOINC, is_loinc),
    (Vocabulary.SNOMED, is_snomed),
    (Vocabulary.ICD10, is_icd10),
    (Vocabulary.ICD9, is_icd9),
    (Vocabulary.CPT4, is_cpt),
    (Vocabulary.RXNORM, is_rxnorm),
    (Vocabulary.HEALTHTREE, is_healthtree),
    (Vocabulary.FHIR_ADMINISTRATIVE, is_fhir_administrative),
)


def detect_vocabulary(coding: dict[str, Any] | None) -> Vocabulary | None:
    """Return the vocabulary a single FHIR `coding` belongs to, or None.

    Order is significant: more specific vocabularies (LOINC/SNOMED/RxNorm)
    are tested before the generic `hl7.org` administrative pattern, which
    LOINC's `http://loinc.org` would otherwise match via the `hl7.org`
    fallback (it wouldn't here, since LOINC doesn't contain "hl7.org",
    but the principle holds for SNOMED's `http://snomed.info/sct`).
    """
    if not coding:
        return None
    for vocab, predicate in _DETECTORS:
        if predicate(coding):
            return vocab
    return None
