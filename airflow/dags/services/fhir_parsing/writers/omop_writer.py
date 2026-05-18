import logging
from datetime import datetime
from typing import Any

from entities.omop.condition_occurrence import ConditionOccurrence
from entities.omop.drug_exposure import DrugExposure
from entities.omop.measurement import Measurement
from entities.omop.patient_info import PatientInfo
from entities.omop.person import Person
from entities.omop.procedure_occurrence import ProcedureOccurrence
from entities.omop.provenance_record import ProvenanceRecord
from infrastructure.repository.omop import (
    ConceptRepository,
    PersonRepository,
    ProvenanceRepository,
)
from services.fhir_parsing.codesystems import is_loinc, is_snomed
from services.fhir_parsing.fhir_parsing_types import (
    Coding,
    FhirPatientIngestionResult,
    ParsedCondition,
    ParsedDrugExposure,
    ParsedMeasurement,
    ParsedPatientPayload,
    ParsedProcedure,
    ProvenanceContext,
)
from services.fhir_parsing.writers._concept_resolver import ConceptResolver, GenericConcept
from services.fhir_parsing.writers.abstract_omop_writer import AbstractOmopWriter

_logger = logging.getLogger(__name__)

# (app_label, model) tuples for Django's ContentType lookup.
_PERSON_CT = ("omop_core", "person")
_PATIENT_INFO_CT = ("omop_core", "patientinfo")
_CONDITION_CT = ("omop_core", "conditionoccurrence")
_MEASUREMENT_CT = ("omop_core", "measurement")
_DRUG_EXPOSURE_CT = ("omop_core", "drugexposure")
_PROCEDURE_CT = ("omop_core", "procedureoccurrence")


class OmopWriter(AbstractOmopWriter):
    """Persists a `ParsedPatientPayload` into the OMOP tables.

    Three injected repositories: `PersonRepository` (Person + PatientInfo +
    per-person clinical events), `ConceptRepository` (read-only vocabulary
    lookup), `ProvenanceRepository` (audit trail).

    Behavior on missing concept:
    Mirrors the Django `upload_fhir` view's cascade — try each coding by
    (system→vocab, code), then by `concept_name ILIKE %code.text%`, then by
    a resource-appropriate generic fallback. If the generic fallback itself
    isn't present in `concept`, the row is skipped with a warning. Idempotent
    on the Django view's natural keys.

    Episode / EpisodeEvent (line-of-therapy bundling) is deferred — standard
    FHIR bundles don't carry reliable LOT metadata.
    """

    def __init__(
        self,
        person_repository: PersonRepository,
        concept_repository: ConceptRepository,
        provenance_repository: ProvenanceRepository,
    ):
        self._person_repository = person_repository
        self._concept_repository = concept_repository
        self._provenance_repository = provenance_repository
        self._concepts = ConceptResolver(concept_repository)

    # --- top-level orchestration -----------------------------------------

    def write_patient(
        self,
        payload: ParsedPatientPayload,
        provenance: ProvenanceContext,
    ) -> FhirPatientIngestionResult:
        result = FhirPatientIngestionResult(fhir_patient_id=payload.person.fhir_id)

        person, is_new = self._upsert_person(payload)
        assert person.person_id is not None
        result.person_id = person.person_id
        result.is_new = is_new
        self._record_provenance(_PERSON_CT, person.person_id, provenance)

        result.condition_ids = self._write_conditions(person.person_id, payload, provenance)
        result.measurement_ids = self._write_measurements(person.person_id, payload, provenance)
        result.drug_exposure_ids = self._write_drug_exposures(person.person_id, payload, provenance)
        result.procedure_ids = self._write_procedures(person.person_id, payload, provenance)

        patient_info = self._apply_patient_info_patch(
            person.person_id, payload.patient_info_patch, provenance.organization_id
        )
        if patient_info is not None and patient_info.id is not None:
            result.patient_info_id = patient_info.id
            self._record_provenance(_PATIENT_INFO_CT, patient_info.id, provenance)

        return result

    # --- person + patient_info -------------------------------------------

    def _upsert_person(self, payload: ParsedPatientPayload) -> tuple[Person, bool]:
        parsed = payload.person
        existing = self._person_repository.find_by_name_and_birth_year(
            given_name=parsed.given_name,
            family_name=parsed.family_name,
            year_of_birth=parsed.year_of_birth,
        )
        is_new = existing is None
        person = existing or Person()
        person.given_name = parsed.given_name
        person.family_name = parsed.family_name
        person.year_of_birth = parsed.year_of_birth
        person.month_of_birth = parsed.month_of_birth
        person.day_of_birth = parsed.day_of_birth
        person.gender_source_value = parsed.gender_source_value
        if parsed.gender_source_value:
            person.gender_concept_id = self._concepts.resolve_gender(parsed.gender_source_value)

        # US Core race/ethnicity → concept_id + source_value. Look up by
        # canonical OMB name; the dev DB has 'Asian', 'Black or African American',
        # 'White' + 'Hispanic or Latino' / 'Not Hispanic or Latino'. Missing
        # buckets (Native Hawaiian, American Indian) leave concept_id null.
        if parsed.race and parsed.race.canonical:
            race_label = parsed.race.canonical[0]
            person.race_source_value = race_label[:50]
            concept = self._concept_repository.find_by_name(race_label)
            if concept is not None and concept.vocabulary_id == "Race":
                person.race_concept_id = concept.concept_id
        if parsed.ethnicity and parsed.ethnicity.canonical:
            eth_label = parsed.ethnicity.canonical[0]
            person.ethnicity_source_value = eth_label[:50]
            concept = self._concept_repository.find_by_name(eth_label)
            if concept is not None and concept.vocabulary_id == "Ethnicity":
                person.ethnicity_concept_id = concept.concept_id

        return self._person_repository.upsert(person), is_new

    def _apply_patient_info_patch(
        self,
        person_id: int,
        patch: dict[str, Any],
        organization_id: int | None,
    ) -> PatientInfo | None:
        if not patch and organization_id is None:
            return None
        return self._person_repository.apply_patient_info_patch(
            person_id=person_id,
            patch=patch,
            organization_id=organization_id,
        )

    # --- conditions ------------------------------------------------------

    def _write_conditions(
        self,
        person_id: int,
        payload: ParsedPatientPayload,
        provenance: ProvenanceContext,
    ) -> list[int]:
        type_concept_id = self._concepts.get_type_concept(GenericConcept.EHR_VISIT_TYPE)
        if type_concept_id is None:
            return []
        written: list[int] = []
        for parsed in payload.conditions:
            condition_concept_id = self._concepts.resolve(
                parsed.codings,
                fuzzy_text=parsed.code_text,
                fallback=None,  # No generic-condition concept_id — skip if unresolved.
            )
            if condition_concept_id is None:
                _logger.info(
                    "Skipping condition with unresolved code: %r",
                    parsed.code_text or [c.code for c in parsed.codings],
                )
                continue
            start_dt = parsed.onset_datetime or parsed.recorded_date
            if start_dt is None:
                _logger.info("Skipping condition with no onset/recorded date: %r", parsed.code_text)
                continue
            source_value = parsed.code_text or _first_coding_display_or_code(parsed.codings)
            status_source_value = ",".join(parsed.clinical_status) if parsed.clinical_status else None
            condition = self._person_repository.upsert_condition_occurrence(
                ConditionOccurrence(
                    person_id=person_id,
                    condition_concept_id=condition_concept_id,
                    condition_start_date=start_dt.date(),
                    condition_start_datetime=start_dt,
                    condition_type_concept_id=type_concept_id,
                    condition_source_value=source_value,
                    condition_status_source_value=status_source_value,
                )
            )
            assert condition.condition_occurrence_id is not None
            written.append(condition.condition_occurrence_id)
            self._record_provenance(_CONDITION_CT, condition.condition_occurrence_id, provenance)
        return written

    # --- measurements ----------------------------------------------------

    def _write_measurements(
        self,
        person_id: int,
        payload: ParsedPatientPayload,
        provenance: ProvenanceContext,
    ) -> list[int]:
        type_concept_id = self._concepts.get_type_concept(GenericConcept.LAB_TYPE) or (
            self._concepts.get_type_concept(GenericConcept.EHR_VISIT_TYPE)
        )
        if type_concept_id is None:
            return []
        written: list[int] = []
        for parsed in payload.measurements:
            measurement_concept_id = self._concepts.resolve(
                parsed.codings,
                fuzzy_text=parsed.code_text,
                fallback=GenericConcept.LAB_TEST,
            )
            if measurement_concept_id is None:
                _logger.info("Skipping measurement with unresolved code: %r", parsed.code_text)
                continue
            when = parsed.effective_datetime or parsed.effective_period_start
            if when is None:
                _logger.info("Skipping measurement with no effective date: %r", parsed.code_text)
                continue
            value_as_number = parsed.value_quantity.value if parsed.value_quantity else None
            unit_source_value = parsed.value_quantity.unit if parsed.value_quantity else None
            value_as_string = parsed.value_string or parsed.value_codeable_concept_text
            # Prefer LOINC code as `measurement_source_value` (matches Django view).
            source_value = _first_loinc_code(parsed.codings) or parsed.code_text
            value_source_value = None
            if parsed.value_string and parsed.value_string_symbol:
                # Preserve the original inequality in value_source_value.
                value_source_value = parsed.value_string
            measurement = self._person_repository.upsert_measurement(
                Measurement(
                    person_id=person_id,
                    measurement_concept_id=measurement_concept_id,
                    measurement_date=when.date(),
                    measurement_datetime=when,
                    measurement_type_concept_id=type_concept_id,
                    value_as_number=value_as_number,
                    value_as_string=value_as_string,
                    measurement_source_value=source_value,
                    unit_source_value=unit_source_value,
                    value_source_value=value_source_value,
                )
            )
            assert measurement.measurement_id is not None
            written.append(measurement.measurement_id)
            self._record_provenance(_MEASUREMENT_CT, measurement.measurement_id, provenance)
        return written

    # --- drug exposures --------------------------------------------------

    def _write_drug_exposures(
        self,
        person_id: int,
        payload: ParsedPatientPayload,
        provenance: ProvenanceContext,
    ) -> list[int]:
        type_concept_id = self._concepts.get_type_concept(GenericConcept.EHR_DRUG_TYPE) or (
            self._concepts.get_type_concept(GenericConcept.EHR_VISIT_TYPE)
        )
        if type_concept_id is None:
            return []
        written: list[int] = []
        for parsed in payload.drug_exposures:
            drug_concept_id = self._resolve_drug_concept(parsed)
            if drug_concept_id is None:
                _logger.info(
                    "Skipping drug_exposure with unresolved medication: %r",
                    parsed.medication_text,
                )
                continue
            start_dt, end_dt = self._drug_dates(parsed)
            if start_dt is None:
                _logger.info(
                    "Skipping drug_exposure with no start date: %r", parsed.medication_text
                )
                continue
            dose_unit = None
            quantity = None
            sig = None
            route = None
            if parsed.dosages:
                first = parsed.dosages[0]
                sig = first.label
                route = first.route
                if first.dose:
                    dose_unit = first.dose.unit
                    if first.dose.type == "QUANTITY" and isinstance(first.dose.value, (int, float)):
                        quantity = float(first.dose.value)
            drug_exposure = self._person_repository.upsert_drug_exposure(
                DrugExposure(
                    person_id=person_id,
                    drug_concept_id=drug_concept_id,
                    drug_exposure_start_date=start_dt.date(),
                    drug_exposure_start_datetime=start_dt,
                    drug_exposure_end_date=end_dt.date() if end_dt else None,
                    drug_exposure_end_datetime=end_dt,
                    drug_type_concept_id=type_concept_id,
                    stop_reason=parsed.status_reason_text,
                    quantity=quantity,
                    sig=sig,
                    drug_source_value=parsed.medication_text
                    or _first_coding_display_or_code(parsed.medication_codings),
                    route_source_value=route,
                    dose_unit_source_value=dose_unit,
                )
            )
            assert drug_exposure.drug_exposure_id is not None
            written.append(drug_exposure.drug_exposure_id)
            self._record_provenance(_DRUG_EXPOSURE_CT, drug_exposure.drug_exposure_id, provenance)
        return written

    def _resolve_drug_concept(self, parsed: ParsedDrugExposure) -> int | None:
        """Drug concept resolution: prefer pre-extracted RxNorm cross-maps over
        the raw codings (which may have been SNOMED-only)."""
        if parsed.rxnorm_codes:
            for rxcui in parsed.rxnorm_codes:
                concept = self._concept_repository.find_by_code(rxcui, "RxNorm")
                if concept is not None:
                    return concept.concept_id
        return self._concepts.resolve(
            parsed.medication_codings,
            fuzzy_text=parsed.medication_text,
            fallback=None,
        )

    @staticmethod
    def _drug_dates(parsed: ParsedDrugExposure) -> tuple[datetime | None, datetime | None]:
        start = parsed.effective_period_start or parsed.effective_datetime or parsed.authored_on
        end = parsed.effective_period_end
        if start is None and parsed.dosages:
            for dosage in parsed.dosages:
                if dosage.dose and dosage.dose.start:
                    start = dosage.dose.start
                    if dosage.dose.end:
                        end = dosage.dose.end
                    break
        return start, end

    # --- procedures ------------------------------------------------------

    def _write_procedures(
        self,
        person_id: int,
        payload: ParsedPatientPayload,
        provenance: ProvenanceContext,
    ) -> list[int]:
        type_concept_id = self._concepts.get_type_concept(GenericConcept.EHR_VISIT_TYPE)
        if type_concept_id is None:
            return []
        written: list[int] = []
        for parsed in payload.procedures:
            procedure_concept_id = self._resolve_procedure_concept(parsed)
            if procedure_concept_id is None:
                _logger.info("Skipping procedure with unresolved code: %r", parsed.code_text)
                continue
            when = parsed.performed_datetime or parsed.performed_period_start
            if when is None:
                _logger.info("Skipping procedure with no performed date: %r", parsed.code_text)
                continue
            procedure = self._person_repository.upsert_procedure_occurrence(
                ProcedureOccurrence(
                    person_id=person_id,
                    procedure_concept_id=procedure_concept_id,
                    procedure_date=when.date(),
                    procedure_datetime=when,
                    procedure_end_date=(
                        parsed.performed_period_end.date()
                        if parsed.performed_period_end
                        else None
                    ),
                    procedure_end_datetime=parsed.performed_period_end,
                    procedure_type_concept_id=type_concept_id,
                    procedure_source_value=parsed.code_text
                    or _first_coding_display_or_code(parsed.codings),
                )
            )
            assert procedure.procedure_occurrence_id is not None
            written.append(procedure.procedure_occurrence_id)
            self._record_provenance(_PROCEDURE_CT, procedure.procedure_occurrence_id, provenance)
        return written

    def _resolve_procedure_concept(self, parsed: ParsedProcedure) -> int | None:
        """Procedure resolution: prefer the CPT→SNOMED cross-mapped code,
        then fall through the standard cascade."""
        if parsed.snomed_code_from_cpt:
            concept = self._concept_repository.find_by_code(parsed.snomed_code_from_cpt, "SNOMED")
            if concept is not None:
                return concept.concept_id
        return self._concepts.resolve(
            parsed.codings,
            fuzzy_text=parsed.code_text,
            fallback=None,
        )

    # --- provenance ------------------------------------------------------

    def _record_provenance(
        self,
        content_type: tuple[str, str],
        object_id: int,
        provenance: ProvenanceContext,
    ) -> None:
        if provenance.source is None:
            return
        app_label, model = content_type
        self._provenance_repository.create(
            ProvenanceRecord(
                source=provenance.source,
                source_user_id=provenance.source_user_id,
                target_patient_id=provenance.target_patient_id,
                modification_reason=provenance.modification_reason,
                organization_id=provenance.organization_id,
                app_label=app_label,
                model=model,
                object_id=object_id,
            )
        )


def _first_coding_display_or_code(codings: list[Coding]) -> str | None:
    for coded in codings:
        if coded.display:
            return coded.display
    for coded in codings:
        if coded.code:
            return str(coded.code)
    return None


def _first_loinc_code(codings: list[Coding]) -> str | None:
    for coded in codings:
        if is_loinc({"system": coded.system, "code": coded.code}) and coded.code:
            return str(coded.code)
    return None
