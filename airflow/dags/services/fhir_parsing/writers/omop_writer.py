import logging

from entities.omop.patient_info import PatientInfo
from entities.omop.person import Person
from entities.omop.provenance_record import ProvenanceRecord
from infrastructure.repository.omop import (
    PersonRepository,
    ProvenanceRepository,
)
from services.fhir_parsing.fhir_parsing_types import (
    FhirPatientIngestionResult,
    ParsedPatientPayload,
    ProvenanceContext,
)
from services.fhir_parsing.writers.abstract_omop_writer import AbstractOmopWriter

_logger = logging.getLogger(__name__)

# `(app_label, model)` tuples for Django's ContentType lookup. Provenance
# repository resolves these to `content_type_id` at write time.
_PERSON_CT = ("omop_core", "person")
_PATIENT_INFO_CT = ("omop_core", "patientinfo")


class OmopWriter(AbstractOmopWriter):
    """Persists a `ParsedPatientPayload` into the OMOP tables.

    Composes 2 repositories today (collapsed from 9 per-table ports):
    - `PersonRepository`: Person + PatientInfo
    - `ProvenanceRepository`: audit-trail rows

    `ConceptRepository` is intentionally absent — vocabulary lookups (gender,
    LOINC, etc.) aren't exercised by any current writer path. Re-add when a
    handler needs concept resolution.

    The current implementation covers the Patient handler slice (Person row +
    PatientInfo patch + provenance). The clinical-event seams
    (`_write_conditions / _write_measurements / _write_drugs_and_episodes`)
    return `[]` until the matching r4 handlers and PersonRepository methods
    are extended.
    """

    def __init__(
        self,
        person_repository: PersonRepository,
        provenance_repository: ProvenanceRepository,
    ):
        self._person_repository = person_repository
        self._provenance_repository = provenance_repository

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
        drug_ids, episode_ids, episode_event_ids = self._write_drugs_and_episodes(
            person.person_id, payload, provenance
        )
        result.drug_exposure_ids = drug_ids
        result.episode_ids = episode_ids
        result.episode_event_ids = episode_event_ids

        patient_info = self._apply_patient_info_patch(
            person.person_id, payload.patient_info_patch, provenance.organization_id
        )
        if patient_info is not None and patient_info.id is not None:
            result.patient_info_id = patient_info.id
            self._record_provenance(_PATIENT_INFO_CT, patient_info.id, provenance)

        return result

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
        # gender_concept_id resolution via ConceptRepository belongs here when implemented.
        return self._person_repository.upsert(person), is_new

    def _write_conditions(self, person_id, payload, provenance) -> list[int]:
        # TODO: port the ConditionOccurrence upsert from the Django view.
        # Extend PersonRepository with `upsert_condition_occurrence` and
        # call _record_provenance(("omop_core", "conditionoccurrence"), id, ...).
        return []

    def _write_measurements(self, person_id, payload, provenance) -> list[int]:
        # TODO: similar to _write_conditions but for the Measurement table.
        return []

    def _write_drugs_and_episodes(self, person_id, payload, provenance):
        # TODO: DrugExposure + Episode + EpisodeEvent. Episodes are LOT groupings.
        return [], [], []

    def _apply_patient_info_patch(
        self,
        person_id: int,
        patch: dict,
        organization_id: int | None,
    ) -> PatientInfo | None:
        if not patch and organization_id is None:
            return None
        return self._person_repository.apply_patient_info_patch(
            person_id=person_id,
            patch=patch,
            organization_id=organization_id,
        )

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
