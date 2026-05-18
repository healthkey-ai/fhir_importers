import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

import infrastructure.repository.omop.person.sql as sql
from entities.omop.condition_occurrence import ConditionOccurrence
from entities.omop.drug_exposure import DrugExposure
from entities.omop.measurement import Measurement
from entities.omop.patient_info import PatientInfo
from entities.omop.person import Person
from entities.omop.procedure_occurrence import ProcedureOccurrence
from infrastructure.repository.base_repository import BaseRepository
from infrastructure.repository.omop.person.repository import PersonRepository

_logger = logging.getLogger(__name__)

_PATIENT_INFO_MANAGED_COLS = {"id", "person_id", "organization_id", "created_at", "updated_at"}

# NOT NULL columns in `patient_info` that don't have a DB-level default and
# therefore must be seeded on INSERT (Django keeps the defaults in Python).
# Mirrors the upload_fhir view's hardcoded baselines (mostly "no/safe"
# assumptions). The patch can still override any of these.
_PATIENT_INFO_REQUIRED_DEFAULTS: dict[str, object] = {
    "no_other_active_malignancies": True,
    "pulmonary_function_test_result": False,
    "bone_imaging_result": False,
    "consent_capability": True,
    "caregiver_availability_status": True,
    "contraceptive_use": False,
    "no_pregnancy_or_lactation_status": True,
    "pregnancy_test_result": False,
    "no_mental_health_disorder_status": True,
    "no_concomitant_medication_status": True,
    "no_tobacco_use_status": True,
    "no_substance_use_status": True,
    "no_geographic_exposure_risk": True,
    "no_hiv_status": True,
    "no_hepatitis_b_status": True,
    "no_hepatitis_c_status": True,
    "no_active_infection_status": True,
    "genetic_mutations": [],  # jsonb — SQLAlchemy serializes Python list
}


class PersonRepositoryImplementation(PersonRepository, BaseRepository):
    """Raw SQL adapter for `person` + `patient_info` + per-person clinical event tables."""

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
            race_concept_id=row["race_concept_id"],
            race_source_value=row["race_source_value"],
            ethnicity_concept_id=row["ethnicity_concept_id"],
            ethnicity_source_value=row["ethnicity_source_value"],
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
            "race_concept_id": person.race_concept_id,
            "race_source_value": person.race_source_value,
            "ethnicity_concept_id": person.ethnicity_concept_id,
            "ethnicity_source_value": person.ethnicity_source_value,
            "location_id": person.location_id,
            "given_name": person.given_name,
            "family_name": person.family_name,
        }
        if person.person_id is None:
            with self._engine.begin() as conn:
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

        # Patch wins over the seed defaults — caller explicitly overrode them.
        required_defaults = {
            k: v for k, v in _PATIENT_INFO_REQUIRED_DEFAULTS.items() if k not in clean_patch
        }

        # Build the UPSERT pieces. `required_*` is seeded on INSERT only;
        # ON CONFLICT updates only the patch columns so an existing row
        # keeps any user-edited defaults instead of being overwritten.
        if required_defaults:
            required_cols = ", ".join(required_defaults.keys()) + ("," if clean_patch else "")
            required_placeholders = ", ".join(f":{k}" for k in required_defaults.keys()) + (
                "," if clean_patch else ""
            )
        else:
            required_cols = ""
            required_placeholders = ""
        if clean_patch:
            patch_cols = ", ".join(clean_patch.keys())
            patch_placeholders = ", ".join(f":{k}" for k in clean_patch.keys())
            patch_update_assignments = ", " + ", ".join(
                f"{k} = EXCLUDED.{k}" for k in clean_patch.keys()
            )
        else:
            patch_cols = ""
            patch_placeholders = ""
            patch_update_assignments = ""

        query = text(
            sql.UPSERT_PATIENT_INFO_TEMPLATE.format(
                required_cols=required_cols,
                required_placeholders=required_placeholders,
                patch_cols=patch_cols,
                patch_placeholders=patch_placeholders,
                patch_update_assignments=patch_update_assignments,
            )
        )
        params = {
            "person_id": person_id,
            "organization_id": organization_id,
            **required_defaults,
            **clean_patch,
        }

        patient_info_id = self._execute_and_scalar_one(query, **params)
        return PatientInfo(
            id=int(patient_info_id),
            person_id=person_id,
            organization_id=organization_id,
            patch=clean_patch,
        )

    # --- clinical events --------------------------------------------------

    def upsert_condition_occurrence(self, condition: ConditionOccurrence) -> ConditionOccurrence:
        assert condition.person_id is not None
        assert condition.condition_concept_id is not None
        assert condition.condition_start_date is not None
        assert condition.condition_type_concept_id is not None
        existing = self._select_one(
            text(sql.SELECT_CONDITION_OCCURRENCE),
            person_id=condition.person_id,
            condition_concept_id=condition.condition_concept_id,
            condition_start_date=condition.condition_start_date,
        )
        params = {
            "person_id": condition.person_id,
            "condition_concept_id": condition.condition_concept_id,
            "condition_start_date": condition.condition_start_date,
            "condition_start_datetime": condition.condition_start_datetime,
            "condition_end_date": condition.condition_end_date,
            "condition_end_datetime": None,
            "condition_type_concept_id": condition.condition_type_concept_id,
            "condition_source_value": _truncate(condition.condition_source_value, 50),
            "condition_status_source_value": _truncate(condition.condition_status_source_value, 50),
        }
        if existing is None:
            with self._engine.begin() as conn:
                next_id = conn.execute(text(sql.NEXT_CONDITION_ID)).scalar_one()
                conn.execute(
                    text(sql.INSERT_CONDITION_OCCURRENCE),
                    {**params, "condition_occurrence_id": next_id},
                )
            condition.condition_occurrence_id = int(next_id)
        else:
            condition.condition_occurrence_id = int(existing["condition_occurrence_id"])
            self._execute(
                text(sql.UPDATE_CONDITION_OCCURRENCE),
                condition_occurrence_id=condition.condition_occurrence_id,
                **{k: params[k] for k in (
                    "condition_start_datetime", "condition_end_date", "condition_end_datetime",
                    "condition_type_concept_id", "condition_source_value",
                    "condition_status_source_value",
                )},
            )
        return condition

    def upsert_measurement(self, measurement: Measurement) -> Measurement:
        assert measurement.person_id is not None
        assert measurement.measurement_concept_id is not None
        assert measurement.measurement_date is not None
        assert measurement.measurement_type_concept_id is not None
        source_value = _truncate(measurement.measurement_source_value, 50)
        existing = self._select_one(
            text(sql.SELECT_MEASUREMENT),
            person_id=measurement.person_id,
            measurement_concept_id=measurement.measurement_concept_id,
            measurement_date=measurement.measurement_date,
            measurement_source_value=source_value,
        )
        params = {
            "person_id": measurement.person_id,
            "measurement_concept_id": measurement.measurement_concept_id,
            "measurement_date": measurement.measurement_date,
            "measurement_datetime": measurement.measurement_datetime,
            "measurement_time": measurement.measurement_time,
            "measurement_type_concept_id": measurement.measurement_type_concept_id,
            "value_as_number": measurement.value_as_number,
            "value_as_string": _truncate(measurement.value_as_string, 60),
            "value_as_concept_id": measurement.value_as_concept_id,
            "unit_concept_id": measurement.unit_concept_id,
            "measurement_source_value": source_value,
            "unit_source_value": _truncate(measurement.unit_source_value, 50),
            "value_source_value": _truncate(measurement.value_source_value, 50),
        }
        if existing is None:
            with self._engine.begin() as conn:
                next_id = conn.execute(text(sql.NEXT_MEASUREMENT_ID)).scalar_one()
                conn.execute(text(sql.INSERT_MEASUREMENT), {**params, "measurement_id": next_id})
            measurement.measurement_id = int(next_id)
        else:
            measurement.measurement_id = int(existing["measurement_id"])
            self._execute(
                text(sql.UPDATE_MEASUREMENT),
                measurement_id=measurement.measurement_id,
                **{k: params[k] for k in (
                    "measurement_datetime", "measurement_time",
                    "measurement_type_concept_id",
                    "value_as_number", "value_as_string", "value_as_concept_id",
                    "unit_concept_id", "unit_source_value", "value_source_value",
                )},
            )
        return measurement

    def upsert_drug_exposure(self, drug_exposure: DrugExposure) -> DrugExposure:
        assert drug_exposure.person_id is not None
        assert drug_exposure.drug_concept_id is not None
        assert drug_exposure.drug_exposure_start_date is not None
        assert drug_exposure.drug_type_concept_id is not None
        existing = self._select_one(
            text(sql.SELECT_DRUG_EXPOSURE),
            person_id=drug_exposure.person_id,
            drug_concept_id=drug_exposure.drug_concept_id,
            drug_exposure_start_date=drug_exposure.drug_exposure_start_date,
        )
        params = {
            "person_id": drug_exposure.person_id,
            "drug_concept_id": drug_exposure.drug_concept_id,
            "drug_exposure_start_date": drug_exposure.drug_exposure_start_date,
            "drug_exposure_start_datetime": drug_exposure.drug_exposure_start_datetime,
            "drug_exposure_end_date": drug_exposure.drug_exposure_end_date,
            "drug_exposure_end_datetime": drug_exposure.drug_exposure_end_datetime,
            "drug_type_concept_id": drug_exposure.drug_type_concept_id,
            "stop_reason": _truncate(drug_exposure.stop_reason, 20),
            "quantity": drug_exposure.quantity,
            "days_supply": drug_exposure.days_supply,
            "sig": drug_exposure.sig,
            "route_concept_id": drug_exposure.route_concept_id,
            "drug_source_value": _truncate(drug_exposure.drug_source_value, 50),
            "route_source_value": _truncate(drug_exposure.route_source_value, 50),
            "dose_unit_source_value": _truncate(drug_exposure.dose_unit_source_value, 50),
        }
        if existing is None:
            with self._engine.begin() as conn:
                next_id = conn.execute(text(sql.NEXT_DRUG_EXPOSURE_ID)).scalar_one()
                conn.execute(text(sql.INSERT_DRUG_EXPOSURE), {**params, "drug_exposure_id": next_id})
            drug_exposure.drug_exposure_id = int(next_id)
        else:
            drug_exposure.drug_exposure_id = int(existing["drug_exposure_id"])
            self._execute(
                text(sql.UPDATE_DRUG_EXPOSURE),
                drug_exposure_id=drug_exposure.drug_exposure_id,
                **{k: params[k] for k in (
                    "drug_exposure_start_datetime",
                    "drug_exposure_end_date", "drug_exposure_end_datetime",
                    "drug_type_concept_id", "stop_reason", "quantity",
                    "days_supply", "sig", "route_concept_id",
                    "drug_source_value", "route_source_value", "dose_unit_source_value",
                )},
            )
        return drug_exposure

    def upsert_procedure_occurrence(
        self,
        procedure: ProcedureOccurrence,
    ) -> ProcedureOccurrence:
        assert procedure.person_id is not None
        assert procedure.procedure_concept_id is not None
        assert procedure.procedure_date is not None
        assert procedure.procedure_type_concept_id is not None
        existing = self._select_one(
            text(sql.SELECT_PROCEDURE_OCCURRENCE),
            person_id=procedure.person_id,
            procedure_concept_id=procedure.procedure_concept_id,
            procedure_date=procedure.procedure_date,
        )
        params = {
            "person_id": procedure.person_id,
            "procedure_concept_id": procedure.procedure_concept_id,
            "procedure_date": procedure.procedure_date,
            "procedure_datetime": procedure.procedure_datetime,
            "procedure_end_date": procedure.procedure_end_date,
            "procedure_end_datetime": procedure.procedure_end_datetime,
            "procedure_type_concept_id": procedure.procedure_type_concept_id,
            "quantity": procedure.quantity,
            "procedure_source_value": _truncate(procedure.procedure_source_value, 50),
            "modifier_source_value": _truncate(procedure.modifier_source_value, 50),
        }
        if existing is None:
            with self._engine.begin() as conn:
                next_id = conn.execute(text(sql.NEXT_PROCEDURE_ID)).scalar_one()
                conn.execute(
                    text(sql.INSERT_PROCEDURE_OCCURRENCE),
                    {**params, "procedure_occurrence_id": next_id},
                )
            procedure.procedure_occurrence_id = int(next_id)
        else:
            procedure.procedure_occurrence_id = int(existing["procedure_occurrence_id"])
            self._execute(
                text(sql.UPDATE_PROCEDURE_OCCURRENCE),
                procedure_occurrence_id=procedure.procedure_occurrence_id,
                **{k: params[k] for k in (
                    "procedure_datetime", "procedure_end_date", "procedure_end_datetime",
                    "procedure_type_concept_id", "quantity",
                    "procedure_source_value", "modifier_source_value",
                )},
            )
        return procedure


def _truncate(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    text_value = str(value)
    return text_value[:max_length] if len(text_value) > max_length else text_value
