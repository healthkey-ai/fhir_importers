"""r4 Patient handler.

Combines:
- ctomop-internal Patient extensions (ethnicity / bodyWeight / bodyHeight /
  systolic-bp / diastolic-bp / heartRate / ecog-performance-status) →
  `patient_info_patch`.
- US Core race + ethnicity extensions (ported from legacy
  `utils/usCoreDemographics.js`) → `ParsedPerson.race` / `.ethnicity`.
- Demographics: names (multi-given normalization), birth date, gender,
  marital status, telecom, contacts, addresses, deceased.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable

from services.fhir_parsing.fhir_parsing_types import (
    HumanName,
    ParsedPatientPayload,
)
from services.fhir_parsing.handlers.abstract_resource_handler import AbstractResourceHandler
from services.fhir_parsing.handlers._datetime_parse import parse_datetime
from services.fhir_parsing.handlers.r4._us_core_demographics import (
    extract_ethnicity,
    extract_race,
)

_logger = logging.getLogger(__name__)

_PATIENT_EXTENSION_BASE = "http://ctomop.io/fhir/StructureDefinition/"

_ExtensionParser = Callable[[dict[str, Any]], Any]

_PATIENT_INFO_EXTENSIONS: dict[str, tuple[str, _ExtensionParser]] = {
    f"{_PATIENT_EXTENSION_BASE}ethnicity": (
        "ethnicity",
        lambda e: e.get("valueString"),
    ),
    f"{_PATIENT_EXTENSION_BASE}bodyWeight": (
        "weight",
        lambda e: (e.get("valueQuantity") or {}).get("value"),
    ),
    f"{_PATIENT_EXTENSION_BASE}bodyHeight": (
        "height",
        lambda e: (e.get("valueQuantity") or {}).get("value"),
    ),
    f"{_PATIENT_EXTENSION_BASE}systolic-bp": (
        "systolic_blood_pressure",
        lambda e: (e.get("valueQuantity") or {}).get("value"),
    ),
    f"{_PATIENT_EXTENSION_BASE}diastolic-bp": (
        "diastolic_blood_pressure",
        lambda e: (e.get("valueQuantity") or {}).get("value"),
    ),
    f"{_PATIENT_EXTENSION_BASE}heartRate": (
        "heartrate",
        lambda e: (e.get("valueQuantity") or {}).get("value"),
    ),
    f"{_PATIENT_EXTENSION_BASE}ecog-performance-status": (
        "ecog_performance_status",
        lambda e: e.get("valueInteger"),
    ),
}


def _normalize_names(name_entries: list[dict[str, Any]]) -> tuple[
    list[HumanName], str | None, str | None, str | None
]:
    """Returns (list of HumanName, first_given, middle_given, family).

    Match heuristic mirrors legacy `getName`: prefer `use='official'`, else
    `use='usual'`, else the first entry. From the chosen entry, `given[0]`
    is first name, `given[1:]` joined is middle name.
    """
    parsed: list[HumanName] = []
    for entry in name_entries:
        if not isinstance(entry, dict):
            continue
        parsed.append(
            HumanName(
                use=entry.get("use"),
                text=entry.get("text"),
                family=entry.get("family"),
                given=[g for g in (entry.get("given") or []) if isinstance(g, str)],
                prefix=[p for p in (entry.get("prefix") or []) if isinstance(p, str)],
                suffix=[s for s in (entry.get("suffix") or []) if isinstance(s, str)],
            )
        )

    if not parsed:
        return [], None, None, None

    preferred = next((n for n in parsed if n.use == "official"), None)
    if preferred is None:
        preferred = next((n for n in parsed if n.use == "usual"), None)
    if preferred is None:
        preferred = parsed[0]

    first = preferred.given[0] if preferred.given else None
    middle = " ".join(preferred.given[1:]) if len(preferred.given) > 1 else None
    family = preferred.family
    return parsed, first, middle, family


class PatientResourceHandler(AbstractResourceHandler):
    def handle(self, resource: dict[str, Any], payload: ParsedPatientPayload) -> None:
        person = payload.person
        person.fhir_id = resource.get("id") or person.fhir_id

        names, first, middle, family = _normalize_names(resource.get("name") or [])
        person.names = names
        person.given_name = first
        person.middle_name = middle
        person.family_name = family
        person.gender_source_value = resource.get("gender")
        person.marital_status_text = (resource.get("maritalStatus") or {}).get("text")

        if resource.get("birthDate"):
            try:
                birth = datetime.strptime(resource["birthDate"], "%Y-%m-%d").date()
                person.birth_date = birth
                person.year_of_birth = birth.year
                person.month_of_birth = birth.month
                person.day_of_birth = birth.day
            except ValueError:
                _logger.warning("Unparseable Patient.birthDate %r", resource.get("birthDate"))

        # Deceased — FHIR is `deceasedBoolean` XOR `deceasedDateTime`.
        if "deceasedBoolean" in resource:
            person.deceased_boolean = bool(resource["deceasedBoolean"])
        if "deceasedDateTime" in resource:
            dt = parse_datetime(resource["deceasedDateTime"])
            if dt is not None:
                person.deceased_datetime = dt
                if person.deceased_boolean is None:
                    person.deceased_boolean = True

        addresses = resource.get("address") or []
        if addresses:
            primary = addresses[0]
            person.address = {
                "country": primary.get("country"),
                "state": primary.get("state"),
                "city": primary.get("city"),
                "postal_code": primary.get("postalCode"),
            }
            person.addresses = [a for a in addresses if isinstance(a, dict)]

        person.telecom = [t for t in (resource.get("telecom") or []) if isinstance(t, dict)]
        person.contacts = [c for c in (resource.get("contact") or []) if isinstance(c, dict)]

        # Email from telecom system='email'.
        for entry in person.telecom:
            if entry.get("system") == "email" and entry.get("value"):
                person.email = entry["value"]
                break

        # US Core race + ethnicity (only if present in `extension`).
        race = extract_race(resource)
        if race is not None:
            person.race = race
        ethnicity = extract_ethnicity(resource)
        if ethnicity is not None:
            person.ethnicity = ethnicity

        # ctomop-internal extensions → patient_info_patch.
        for ext in resource.get("extension") or []:
            url = ext.get("url", "") if isinstance(ext, dict) else ""
            mapping = _PATIENT_INFO_EXTENSIONS.get(url)
            if mapping is None:
                continue
            field, parser = mapping
            value = parser(ext)
            if value is not None:
                payload.patient_info_patch[field] = value

        # Default units when weight/height arrive without explicit units
        # (mirrors the Django upload_fhir view: it stamps 'kg'/'cm').
        if "weight" in payload.patient_info_patch and "weight_units" not in payload.patient_info_patch:
            payload.patient_info_patch["weight_units"] = "kg"
        if "height" in payload.patient_info_patch and "height_units" not in payload.patient_info_patch:
            payload.patient_info_patch["height_units"] = "cm"
