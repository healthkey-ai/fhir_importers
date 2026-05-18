"""Static cross-vocabulary mapping tables.

`cpt_to_snomed_map.json` and `snomed_to_rxnorm_map.json` are copied verbatim
from `legacy/.../FHIR/codeSystems/` and loaded lazily on first use.

Shapes (mirror the JS):
- `cpt_to_snomed_map.json`:   { "<cptCode>": { "cptConceptId": "...", "cptCode": "...", "cptDescriptor": "...", "snomedId": "...", "snomedDescriptor": "..." }, ... }
  → `cpt_to_snomed("10004")` returns "0" or a numeric SNOMED id string.
- `snomed_to_rxnorm_map.json`: { "<snomedCode>": "<rxnormCode>", ... }
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from services.fhir_parsing.codesystems.vocabularies import is_rxnorm, is_snomed

_HERE = Path(__file__).parent


@lru_cache(maxsize=1)
def _cpt_to_snomed_table() -> dict[str, dict[str, Any]]:
    return json.loads((_HERE / "cpt_to_snomed_map.json").read_text())


@lru_cache(maxsize=1)
def _snomed_to_rxnorm_table() -> dict[str, str]:
    return json.loads((_HERE / "snomed_to_rxnorm_map.json").read_text())


def cpt_to_snomed(cpt_code: str | None) -> str | None:
    """Map a CPT-4 code to its SNOMED equivalent. Returns None when the
    legacy table lacks a mapping (or when the mapping value is "0", the
    legacy sentinel for "no SNOMED equivalent")."""
    if not cpt_code:
        return None
    entry = _cpt_to_snomed_table().get(str(cpt_code))
    if not entry:
        return None
    snomed = entry.get("snomedId")
    if not snomed or snomed == "0":
        return None
    return str(snomed)


def snomed_to_rxnorm(snomed_code: str | None) -> str | None:
    """Map a SNOMED concept code to an RxNorm code. None when missing."""
    if not snomed_code:
        return None
    rxnorm = _snomed_to_rxnorm_table().get(str(snomed_code))
    return str(rxnorm) if rxnorm else None


def rxnorm_from_codings(codings: Iterable[dict[str, Any]] | None) -> list[str]:
    """Extract RxNorm codes from a FHIR coding[] (port of `processCodingToRXCUI.js`).

    For each coding:
    - if it's already RxNorm, keep its `code` as-is;
    - if it's SNOMED, look up the RxNorm equivalent via `snomed_to_rxnorm_map`.
    Returns a deduplicated list preserving insertion order.
    """
    if not codings:
        return []
    seen: dict[str, None] = {}
    for coding in codings:
        if is_snomed(coding):
            mapped = snomed_to_rxnorm(coding.get("code"))
            if mapped:
                seen[mapped] = None
        elif is_rxnorm(coding):
            code = coding.get("code")
            if code:
                seen[str(code)] = None
    return list(seen.keys())
