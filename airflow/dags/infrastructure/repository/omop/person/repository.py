import abc
from typing import Any

from entities.omop.patient_info import PatientInfo
from entities.omop.person import Person


class PersonRepository(abc.ABC):
    """Port for the OMOP `person` table plus the `patient_info` summary that
    is 1:1 with Person. The Django app owns the schema.

    PatientInfo lives here because it's denormalized per-Person data; collapsing
    avoids the per-table-repo explosion (Person, PatientInfo, ConditionOccurrence,
    Measurement, DrugExposure, Episode, ... were all separate ports earlier and
    that fanned out faster than the FHIR pipeline needed).
    """

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
        """Insert if `person_id` is None (allocate next id), otherwise UPDATE.
        Returns the persisted row with `person_id` populated."""
        raise NotImplementedError

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
        """Upsert a `patient_info` row for `person_id`, overlaying `patch` keys.

        Must NOT touch columns not present in `patch` (Django keeps OMOP-derived
        fields authoritative via its own refresh signals).
        """
        raise NotImplementedError
