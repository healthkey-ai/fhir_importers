from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from entities.omop.provenance_record import ProvenanceSource


class FhirVersion(StrEnum):
    """FHIR versions the service may dispatch on."""

    DSTU2 = "dstu2"
    STU3 = "stu3"
    R4 = "r4"


class FhirResourceType(StrEnum):
    PATIENT = "Patient"
    CONDITION = "Condition"
    OBSERVATION = "Observation"
    MEDICATION_STATEMENT = "MedicationStatement"
    MEDICATION_REQUEST = "MedicationRequest"
    MEDICATION_ORDER = "MedicationOrder"  # DSTU2 only
    PROCEDURE = "Procedure"


class ProvenanceContext(BaseModel):
    """Provenance metadata attached to every OMOP row the ingestion writes."""

    source: ProvenanceSource | None = None
    source_user_id: str = ""
    target_patient_id: str | None = None
    organization_id: int | None = None
    modification_reason: str | None = None


# ---------------------------------------------------------------------------
# Coding — the FHIR primitive every clinical resource carries.
# ---------------------------------------------------------------------------


class Coding(BaseModel):
    """A single FHIR `Coding` entry, preserved verbatim for the writer to
    resolve into an OMOP `concept_id` via `ConceptRepository.find_by_code(...)`.

    The handler doesn't translate codes — that's a write-time concern. The
    `system` field is what the writer maps to a `vocabulary_id`; downstream
    helpers in `services.fhir_parsing.codesystems` test it for membership.
    """

    system: str | None = None
    code: str | None = None
    display: str | None = None


def coding_from_dict(coding: dict[str, Any] | None) -> Coding | None:
    if not coding:
        return None
    return Coding(
        system=coding.get("system"),
        code=str(coding["code"]) if coding.get("code") is not None else None,
        display=coding.get("display"),
    )


def codings_from_codeable_concept(cc: dict[str, Any] | None) -> list[Coding]:
    """`coding[]` extraction from a CodeableConcept, dropping empty entries."""
    if not cc:
        return []
    result: list[Coding] = []
    for raw in cc.get("coding") or []:
        coded = coding_from_dict(raw)
        if coded and (coded.code or coded.display):
            result.append(coded)
    return result


# ---------------------------------------------------------------------------
# ParsedPerson
# ---------------------------------------------------------------------------


class HumanName(BaseModel):
    """Mirror of FHIR HumanName, after `getName` normalization."""

    use: str | None = None
    text: str | None = None
    family: str | None = None
    given: list[str] = Field(default_factory=list)
    prefix: list[str] = Field(default_factory=list)
    suffix: list[str] = Field(default_factory=list)


class RaceExtension(BaseModel):
    """Extracted US Core race extension (see `usCoreDemographics.js`)."""

    canonical: list[str] = Field(default_factory=list)
    omb_categories: list[Coding] = Field(default_factory=list)
    detailed: list[Coding] = Field(default_factory=list)
    text_values: list[str] = Field(default_factory=list)


class ParsedPerson(BaseModel):
    fhir_id: str
    given_name: str | None = None
    middle_name: str | None = None
    family_name: str | None = None
    gender_source_value: str | None = None
    birth_date: date | None = None
    year_of_birth: int | None = None
    month_of_birth: int | None = None
    day_of_birth: int | None = None
    deceased_boolean: bool | None = None
    deceased_datetime: datetime | None = None
    marital_status_text: str | None = None
    email: str | None = None
    address: dict[str, Any] = Field(default_factory=dict)
    addresses: list[dict[str, Any]] = Field(default_factory=list)
    names: list[HumanName] = Field(default_factory=list)
    telecom: list[dict[str, Any]] = Field(default_factory=list)
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    race: RaceExtension | None = None
    ethnicity: RaceExtension | None = None


# ---------------------------------------------------------------------------
# ParsedCondition
# ---------------------------------------------------------------------------


class ParsedCondition(BaseModel):
    code_text: str | None = None
    codings: list[Coding] = Field(default_factory=list)
    onset_datetime: datetime | None = None
    recorded_date: datetime | None = None
    clinical_status: list[str] = Field(default_factory=list)
    verification_status: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    stage_text: str | None = None
    extension: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ParsedMeasurement (Observation)
# ---------------------------------------------------------------------------


class ParsedValueQuantity(BaseModel):
    value: float | None = None
    unit: str | None = None
    code: str | None = None
    system: str | None = None
    comparator: str | None = None


class ParsedRange(BaseModel):
    low: ParsedValueQuantity | None = None
    high: ParsedValueQuantity | None = None


class ParsedRatio(BaseModel):
    numerator: ParsedValueQuantity | None = None
    denominator: ParsedValueQuantity | None = None


class ParsedMeasurementComponent(BaseModel):
    """One component of a multi-part Observation (e.g. systolic+diastolic BP).
    Recursive parsing follows the same value-variant pattern as the top level."""

    codings: list[Coding] = Field(default_factory=list)
    code_text: str | None = None
    value_quantity: ParsedValueQuantity | None = None
    value_boolean: bool | None = None
    value_string: str | None = None
    value_integer: int | None = None
    value_codeable_concept_text: str | None = None
    value_codeable_concept_codings: list[Coding] = Field(default_factory=list)
    interpretation: list[Coding] = Field(default_factory=list)


class ParsedMeasurement(BaseModel):
    """One Observation resource, parsed.

    UCUM unit conversion is deferred — `value_quantity.unit` is whatever the
    source FHIR gave us. The writer (when it gains a UCUM helper) maps the
    LOINC code's `standardUnit` and converts.
    """

    codings: list[Coding] = Field(default_factory=list)
    code_text: str | None = None
    status: str | None = None
    effective_datetime: datetime | None = None
    effective_period_start: datetime | None = None
    effective_period_end: datetime | None = None
    value_quantity: ParsedValueQuantity | None = None
    value_boolean: bool | None = None
    value_string: str | None = None
    value_string_symbol: str | None = None  # '<' / '>' / '<=' / '>=' from rescue heuristic
    value_integer: int | None = None
    value_codeable_concept_text: str | None = None
    value_codeable_concept_codings: list[Coding] = Field(default_factory=list)
    value_range: ParsedRange | None = None
    value_ratio: ParsedRatio | None = None
    value_datetime: datetime | None = None
    value_time: str | None = None
    value_period_start: datetime | None = None
    value_period_end: datetime | None = None
    value_sampled_data: dict[str, Any] | None = None
    interpretation: list[Coding] = Field(default_factory=list)
    note: list[str] = Field(default_factory=list)
    components: list[ParsedMeasurementComponent] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ParsedDrugExposure / ParsedEpisode
# ---------------------------------------------------------------------------


class ParsedDose(BaseModel):
    """Output of the dosage-instruction parser, mirroring legacy
    `MedicationRequest/getNormalization.js::createDoses` field-by-field."""

    value: float | dict[str, Any] | None = None  # scalar for QUANTITY, range dict for RANGE
    unit: str | None = None
    type: str | None = None  # 'QUANTITY' | 'RANGE'
    frequency: int | None = None
    period: float | None = None
    period_unit: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    text: str | None = None
    summary: str | None = None


class ParsedDosage(BaseModel):
    label: str | None = None
    route: str | None = None
    dose: ParsedDose | None = None


class ParsedDrugExposure(BaseModel):
    medication_text: str | None = None
    medication_codings: list[Coding] = Field(default_factory=list)
    rxnorm_codes: list[str] = Field(default_factory=list)
    status: str | None = None
    status_reason_text: str | None = None
    effective_datetime: datetime | None = None
    effective_period_start: datetime | None = None
    effective_period_end: datetime | None = None
    authored_on: datetime | None = None
    notes: list[str] = Field(default_factory=list)
    dosages: list[ParsedDosage] = Field(default_factory=list)
    line_of_therapy: int | None = None


class ParsedEpisode(BaseModel):
    source_value: str
    start_date: date | None = None
    end_date: date | None = None
    episode_number: int | None = None


# ---------------------------------------------------------------------------
# ParsedProcedure
# ---------------------------------------------------------------------------


class ParsedProcedure(BaseModel):
    codings: list[Coding] = Field(default_factory=list)
    code_text: str | None = None
    snomed_code_from_cpt: str | None = None  # via cpt_to_snomed lookup
    status: str | None = None
    performed_datetime: datetime | None = None
    performed_period_start: datetime | None = None
    performed_period_end: datetime | None = None
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ParsedPatientPayload
# ---------------------------------------------------------------------------


class ParsedPatientPayload(BaseModel):
    """Per-patient intermediate result of bundle parsing.

    Handlers accumulate into this object; `OmopWriter` consumes it.
    `patient_info_patch` holds denormalized fields without an OMOP home yet.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    person: ParsedPerson
    conditions: list[ParsedCondition] = Field(default_factory=list)
    measurements: list[ParsedMeasurement] = Field(default_factory=list)
    drug_exposures: list[ParsedDrugExposure] = Field(default_factory=list)
    procedures: list[ParsedProcedure] = Field(default_factory=list)
    episodes: list[ParsedEpisode] = Field(default_factory=list)
    patient_info_patch: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Result types (unchanged surface; new fields appended)
# ---------------------------------------------------------------------------


class FhirPatientIngestionResult(BaseModel):
    fhir_patient_id: str
    person_id: int | None = None
    patient_info_id: int | None = None
    is_new: bool = False
    measurement_ids: list[int] = Field(default_factory=list)
    condition_ids: list[int] = Field(default_factory=list)
    drug_exposure_ids: list[int] = Field(default_factory=list)
    procedure_ids: list[int] = Field(default_factory=list)
    episode_ids: list[int] = Field(default_factory=list)
    episode_event_ids: list[int] = Field(default_factory=list)
    error: str | None = None


class FhirIngestionResult(BaseModel):
    created_count: int = 0
    updated_count: int = 0
    patients: list[FhirPatientIngestionResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
