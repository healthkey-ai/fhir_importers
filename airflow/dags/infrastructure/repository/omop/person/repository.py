import abc
from typing import Any

from entities.omop.condition_occurrence import ConditionOccurrence
from entities.omop.drug_exposure import DrugExposure
from entities.omop.measurement import Measurement
from entities.omop.patient_info import PatientInfo
from entities.omop.person import Person
from entities.omop.procedure_occurrence import ProcedureOccurrence


class PersonRepository(abc.ABC):
    """Port for the OMOP `person` table + everything anchored to a single Person.

    Groups by major entity (the user's directive after we found ourselves with
    9 per-table ports). Covers `person`, `patient_info` (1:1 with Person),
    plus the per-person clinical event tables: `condition_occurrence`,
    `measurement`, `drug_exposure`, `procedure_occurrence`. `episode` and
    `episode_event` are deferred — FHIR bundles don't carry reliable
    line-of-therapy metadata for bundling.
    """

    # --- person -----------------------------------------------------------

    @abc.abstractmethod
    def find_by_name_and_birth_year(
        self,
        given_name: str | None,
        family_name: str | None,
        year_of_birth: int | None,
    ) -> Person | None:
        raise NotImplementedError

    @abc.abstractmethod
    def upsert(self, person: Person) -> Person:
        """Insert if `person_id` is None (allocate next id), otherwise UPDATE."""
        raise NotImplementedError

    # --- patient_info -----------------------------------------------------

    @abc.abstractmethod
    def get_patient_info_by_person_id(self, person_id: int) -> PatientInfo | None:
        raise NotImplementedError

    @abc.abstractmethod
    def apply_patient_info_patch(
        self,
        person_id: int,
        patch: dict[str, Any],
        organization_id: int | None,
    ) -> PatientInfo:
        raise NotImplementedError

    # --- per-person clinical events --------------------------------------
    # All four upserts are idempotent on the Django view's natural keys:
    # - condition_occurrence: (person_id, condition_concept_id, condition_start_date)
    # - measurement:          (person_id, measurement_concept_id, measurement_date,
    #                          measurement_source_value)
    # - drug_exposure:        (person_id, drug_concept_id, drug_exposure_start_date)
    # - procedure_occurrence: (person_id, procedure_concept_id, procedure_date)

    @abc.abstractmethod
    def upsert_condition_occurrence(self, condition: ConditionOccurrence) -> ConditionOccurrence:
        raise NotImplementedError

    @abc.abstractmethod
    def upsert_measurement(self, measurement: Measurement) -> Measurement:
        raise NotImplementedError

    @abc.abstractmethod
    def upsert_drug_exposure(self, drug_exposure: DrugExposure) -> DrugExposure:
        raise NotImplementedError

    @abc.abstractmethod
    def upsert_procedure_occurrence(
        self,
        procedure: ProcedureOccurrence,
    ) -> ProcedureOccurrence:
        raise NotImplementedError
