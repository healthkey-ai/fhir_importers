import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

import infrastructure.repository.omop.person.sql as sql
from entities.omop.patient_info import PatientInfo
from entities.omop.person import Person
from infrastructure.repository.base_repository import BaseRepository
from infrastructure.repository.omop.person.repository import PersonRepository

_logger = logging.getLogger(__name__)

# `patient_info` columns the FHIR pipeline never sets directly (they're
# either auto-managed or have NOT-NULL defaults that need to be honored on
# INSERT). Listed explicitly so a typo in a patch key fails loudly instead
# of silently writing to a wrong column.
_PATIENT_INFO_MANAGED_COLS = {"id", "person_id", "organization_id", "created_at", "updated_at"}


class PersonRepositoryImplementation(PersonRepository, BaseRepository):
    """Raw SQL adapter against the Django-owned `person` + `patient_info` tables."""

    def __init__(self, engine: Engine):
        super().__init__(engine)
        self._engine = engine

    # --- person -----------------------------------------------------------

    def find_by_name_and_birth_year(
        self,
        given_name: str | None,
        family_name: str | None,
        year_of_birth: int | None,
    ) -> Person | None:
        row = self._select_one(
            text(sql.SELECT_PERSON_BY_NAME_AND_BIRTH_YEAR),
            given_name=given_name,
            family_name=family_name,
            year_of_birth=year_of_birth,
        )
        if row is None:
            return None
        return Person(
            person_id=row["person_id"],
            gender_concept_id=row["gender_concept_id"],
            gender_source_value=row["gender_source_value"],
            year_of_birth=row["year_of_birth"],
            month_of_birth=row["month_of_birth"],
            day_of_birth=row["day_of_birth"],
            birth_datetime=row["birth_datetime"],
            ethnicity_concept_id=row["ethnicity_concept_id"],
            location_id=row["location_id"],
            given_name=row["given_name"],
            family_name=row["family_name"],
        )

    def upsert(self, person: Person) -> Person:
        params = {
            "gender_concept_id": person.gender_concept_id,
            "gender_source_value": person.gender_source_value,
            "year_of_birth": person.year_of_birth,
            "month_of_birth": person.month_of_birth,
            "day_of_birth": person.day_of_birth,
            "birth_datetime": person.birth_datetime,
            "ethnicity_concept_id": person.ethnicity_concept_id,
            "location_id": person.location_id,
            "given_name": person.given_name,
            "family_name": person.family_name,
        }
        if person.person_id is None:
            with self._engine.begin() as conn:
                # MAX(person_id)+1 to match the Django view's allocation
                # pattern (the `person.person_id` column is a non-auto IntegerField).
                next_id = conn.execute(text(sql.NEXT_PERSON_ID)).scalar_one()
                conn.execute(text(sql.INSERT_PERSON), {**params, "person_id": next_id})
            person.person_id = int(next_id)
        else:
            self._execute(text(sql.UPDATE_PERSON_BY_ID), person_id=person.person_id, **params)
        return person

    # --- patient_info -----------------------------------------------------

    def get_patient_info_by_person_id(self, person_id: int) -> PatientInfo | None:
        row = self._select_one(text(sql.SELECT_PATIENT_INFO_BY_PERSON_ID), person_id=person_id)
        if row is None:
            return None
        return PatientInfo(
            id=row["id"],
            person_id=row["person_id"],
            organization_id=row["organization_id"],
        )

    def apply_patient_info_patch(
        self,
        person_id: int,
        patch: dict[str, Any],
        organization_id: int | None,
    ) -> PatientInfo:
        clean_patch = {k: v for k, v in patch.items() if k not in _PATIENT_INFO_MANAGED_COLS}

        if not clean_patch:
            query = text(sql.UPSERT_PATIENT_INFO_EMPTY)
            params = {"person_id": person_id, "organization_id": organization_id}
        else:
            cols = ", ".join(clean_patch.keys())
            placeholders = ", ".join(f":{k}" for k in clean_patch.keys())
            update_assignments = ", ".join(f"{k} = EXCLUDED.{k}" for k in clean_patch.keys())
            query = text(
                sql.UPSERT_PATIENT_INFO_TEMPLATE.format(
                    cols=cols,
                    placeholders=placeholders,
                    update_assignments=update_assignments,
                )
            )
            params = {"person_id": person_id, "organization_id": organization_id, **clean_patch}

        patient_info_id = self._execute_and_scalar_one(query, **params)
        return PatientInfo(id=int(patient_info_id), person_id=person_id, organization_id=organization_id, patch=clean_patch)
