"""r4 Observation handler.

Port of `legacy/.../resourcesTypes/r4/Observation/getNormalization.js`,
minus the UCUM unit conversion (deferred to the writer / a future
`services.fhir_parsing.units` helper).

Surface preserved:
- All FHIR value variants: `valueQuantity`, `valueBoolean`, `valueString`,
  `valueCodeableConcept`, `valueRange`, `valueRatio`, `valueSampledData`,
  `valueTime`, `valueDateTime`, `valuePeriod`, `valueInteger`.
- `effectiveDateTime` / `effectivePeriod.start/end`, `status`, `interpretation[]`,
  `note[]`.
- Recursive `component[]` parsing — each component carries its own code +
  value variants. Codings are collected at the top level and from each
  component for downstream concept resolution.
- `valueString` → `valueQuantity` rescue heuristic for `"<5.0 mg/dL"` patterns.
"""
from __future__ import annotations

import logging
from typing import Any

from services.fhir_parsing.fhir_parsing_types import (
    Coding,
    ParsedMeasurement,
    ParsedMeasurementComponent,
    ParsedPatientPayload,
    coding_from_dict,
    codings_from_codeable_concept,
)
from services.fhir_parsing.handlers._datetime_parse import parse_datetime
from services.fhir_parsing.handlers.abstract_resource_handler import AbstractResourceHandler
from services.fhir_parsing.handlers.r4._observation_value_parse import (
    convert_value_string_to_value_quantity,
    parse_value_quantity_dict,
    parse_value_range_dict,
    parse_value_ratio_dict,
)

_logger = logging.getLogger(__name__)


def _parse_note(note_list: list[dict[str, Any]] | None) -> list[str]:
    out: list[str] = []
    for entry in note_list or []:
        if isinstance(entry, dict) and entry.get("text"):
            out.append(str(entry["text"]))
        elif isinstance(entry, str):
            out.append(entry)
    return out


def _parse_interpretation(raw: Any) -> list[Coding]:
    """`interpretation` is `CodeableConcept[]` in r4. Collect all codings."""
    out: list[Coding] = []
    if isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict):
        entries = [raw]
    else:
        return out
    for entry in entries:
        out.extend(codings_from_codeable_concept(entry))
    return out


def _parse_component(component: dict[str, Any]) -> ParsedMeasurementComponent:
    code = component.get("code") or {}
    vc = component.get("valueCodeableConcept") or {}
    comp = ParsedMeasurementComponent(
        codings=codings_from_codeable_concept(code),
        code_text=code.get("text"),
        value_quantity=parse_value_quantity_dict(component.get("valueQuantity")),
        value_boolean=component.get("valueBoolean"),
        value_string=component.get("valueString"),
        value_integer=component.get("valueInteger"),
        value_codeable_concept_text=vc.get("text"),
        value_codeable_concept_codings=codings_from_codeable_concept(vc),
        interpretation=_parse_interpretation(component.get("interpretation")),
    )
    return comp


class ObservationResourceHandler(AbstractResourceHandler):
    def handle(self, resource: dict[str, Any], payload: ParsedPatientPayload) -> None:
        code = resource.get("code") or {}
        vc = resource.get("valueCodeableConcept") or {}
        period = resource.get("effectivePeriod") or {}
        value_period = resource.get("valuePeriod") or {}

        parsed = ParsedMeasurement(
            codings=codings_from_codeable_concept(code),
            code_text=code.get("text"),
            status=resource.get("status"),
            effective_datetime=parse_datetime(resource.get("effectiveDateTime")),
            effective_period_start=parse_datetime(period.get("start")),
            effective_period_end=parse_datetime(period.get("end")),
            value_quantity=parse_value_quantity_dict(resource.get("valueQuantity")),
            value_boolean=resource.get("valueBoolean"),
            value_string=resource.get("valueString"),
            value_integer=resource.get("valueInteger"),
            value_codeable_concept_text=vc.get("text"),
            value_codeable_concept_codings=codings_from_codeable_concept(vc),
            value_range=parse_value_range_dict(resource.get("valueRange")),
            value_ratio=parse_value_ratio_dict(resource.get("valueRatio")),
            value_datetime=parse_datetime(resource.get("valueDateTime")),
            value_time=resource.get("valueTime"),
            value_period_start=parse_datetime(value_period.get("start")),
            value_period_end=parse_datetime(value_period.get("end")),
            value_sampled_data=resource.get("valueSampledData"),
            interpretation=_parse_interpretation(resource.get("interpretation")),
            note=_parse_note(resource.get("note")),
        )

        # valueString → valueQuantity rescue. Only applies when no real
        # valueQuantity was present (legacy short-circuits the same way).
        if parsed.value_quantity is None and parsed.value_string:
            rescued, symbol = convert_value_string_to_value_quantity(parsed.value_string)
            if rescued is not None:
                parsed.value_quantity = rescued
                parsed.value_string_symbol = symbol

        # Components: parse each, then union their codings into the parent so
        # the writer's concept lookup sees the BP-systolic/diastolic LOINC codes
        # even when the parent code is the panel.
        for component in resource.get("component") or []:
            if not isinstance(component, dict):
                continue
            comp = _parse_component(component)
            parsed.components.append(comp)
            for coding in comp.codings:
                if coding not in parsed.codings:
                    parsed.codings.append(coding)

        if parsed.code_text is None and parsed.codings:
            parsed.code_text = parsed.codings[0].display

        payload.measurements.append(parsed)
