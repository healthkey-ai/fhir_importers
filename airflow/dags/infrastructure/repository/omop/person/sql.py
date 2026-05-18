"""SQL for the Person aggregate.

Targets the Django-owned OMOP schema in ctomop. Tables:
    person                  (PK: person_id; non-auto integer)
    patient_info            (PK: id; UNIQUE: person_id)
    condition_occurrence    (PK: condition_occurrence_id; non-auto bigint)
    measurement             (PK: measurement_id; non-auto bigint)
    drug_exposure           (PK: drug_exposure_id; non-auto bigint)
    procedure_occurrence    (PK: procedure_occurrence_id; non-auto bigint)

All clinical-event PKs are non-auto; we allocate via MAX(id)+1 to match
the Django view's pattern. This is racy in concurrent ingestion — acceptable
for the current single-DAG flow; revisit when we run parallel patient
ingestion.
"""

# --- person -----------------------------------------------------------------

SELECT_PERSON_BY_NAME_AND_BIRTH_YEAR = """
SELECT
    person_id,
    gender_concept_id,
    gender_source_value,
    year_of_birth,
    month_of_birth,
    day_of_birth,
    birth_datetime,
    race_concept_id,
    race_source_value,
    ethnicity_concept_id,
    ethnicity_source_value,
    location_id,
    given_name,
    family_name
FROM person
WHERE given_name IS NOT DISTINCT FROM :given_name
  AND family_name IS NOT DISTINCT FROM :family_name
  AND year_of_birth IS NOT DISTINCT FROM :year_of_birth
ORDER BY person_id
LIMIT 1
"""

NEXT_PERSON_ID = "SELECT COALESCE(MAX(person_id), 999) + 1 AS next_id FROM person"

INSERT_PERSON = """
INSERT INTO person (
    person_id, gender_concept_id, gender_source_value,
    year_of_birth, month_of_birth, day_of_birth, birth_datetime,
    race_concept_id, race_source_value,
    ethnicity_concept_id, ethnicity_source_value,
    location_id, given_name, family_name
) VALUES (
    :person_id, :gender_concept_id, :gender_source_value,
    :year_of_birth, :month_of_birth, :day_of_birth, :birth_datetime,
    :race_concept_id, :race_source_value,
    :ethnicity_concept_id, :ethnicity_source_value,
    :location_id, :given_name, :family_name
)
"""

UPDATE_PERSON_BY_ID = """
UPDATE person SET
    gender_concept_id      = :gender_concept_id,
    gender_source_value    = :gender_source_value,
    year_of_birth          = :year_of_birth,
    month_of_birth         = :month_of_birth,
    day_of_birth           = :day_of_birth,
    birth_datetime         = :birth_datetime,
    race_concept_id        = COALESCE(:race_concept_id, race_concept_id),
    race_source_value      = COALESCE(:race_source_value, race_source_value),
    ethnicity_concept_id   = COALESCE(:ethnicity_concept_id, ethnicity_concept_id),
    ethnicity_source_value = COALESCE(:ethnicity_source_value, ethnicity_source_value),
    location_id            = :location_id,
    given_name             = :given_name,
    family_name            = :family_name
WHERE person_id = :person_id
"""

# --- patient_info ----------------------------------------------------------

SELECT_PATIENT_INFO_BY_PERSON_ID = """
SELECT id, person_id, organization_id
FROM patient_info
WHERE person_id = :person_id
LIMIT 1
"""

UPSERT_PATIENT_INFO_TEMPLATE = """
INSERT INTO patient_info (
    person_id, organization_id, created_at, updated_at,
    {required_cols}
    {patch_cols}
)
VALUES (
    :person_id, :organization_id, NOW(), NOW(),
    {required_placeholders}
    {patch_placeholders}
)
ON CONFLICT (person_id) DO UPDATE SET
    organization_id = COALESCE(EXCLUDED.organization_id, patient_info.organization_id),
    updated_at = NOW()
    {patch_update_assignments}
RETURNING id
"""

# --- condition_occurrence --------------------------------------------------

NEXT_CONDITION_ID = """
SELECT COALESCE(MAX(condition_occurrence_id), 0) + 1 AS next_id FROM condition_occurrence
"""

SELECT_CONDITION_OCCURRENCE = """
SELECT condition_occurrence_id
FROM condition_occurrence
WHERE person_id = :person_id
  AND condition_concept_id = :condition_concept_id
  AND condition_start_date = :condition_start_date
LIMIT 1
"""

INSERT_CONDITION_OCCURRENCE = """
INSERT INTO condition_occurrence (
    condition_occurrence_id, person_id, condition_concept_id,
    condition_start_date, condition_start_datetime,
    condition_end_date, condition_end_datetime,
    condition_type_concept_id,
    condition_source_value, condition_status_source_value
) VALUES (
    :condition_occurrence_id, :person_id, :condition_concept_id,
    :condition_start_date, :condition_start_datetime,
    :condition_end_date, :condition_end_datetime,
    :condition_type_concept_id,
    :condition_source_value, :condition_status_source_value
)
"""

UPDATE_CONDITION_OCCURRENCE = """
UPDATE condition_occurrence SET
    condition_start_datetime      = :condition_start_datetime,
    condition_end_date            = :condition_end_date,
    condition_end_datetime        = :condition_end_datetime,
    condition_type_concept_id     = :condition_type_concept_id,
    condition_source_value        = :condition_source_value,
    condition_status_source_value = :condition_status_source_value
WHERE condition_occurrence_id = :condition_occurrence_id
"""

# --- measurement -----------------------------------------------------------

NEXT_MEASUREMENT_ID = """
SELECT COALESCE(MAX(measurement_id), 0) + 1 AS next_id FROM measurement
"""

SELECT_MEASUREMENT = """
SELECT measurement_id
FROM measurement
WHERE person_id = :person_id
  AND measurement_concept_id = :measurement_concept_id
  AND measurement_date = :measurement_date
  AND measurement_source_value IS NOT DISTINCT FROM :measurement_source_value
LIMIT 1
"""

INSERT_MEASUREMENT = """
INSERT INTO measurement (
    measurement_id, person_id, measurement_concept_id,
    measurement_date, measurement_datetime, measurement_time,
    measurement_type_concept_id,
    value_as_number, value_as_string, value_as_concept_id,
    unit_concept_id,
    measurement_source_value, unit_source_value, value_source_value
) VALUES (
    :measurement_id, :person_id, :measurement_concept_id,
    :measurement_date, :measurement_datetime, :measurement_time,
    :measurement_type_concept_id,
    :value_as_number, :value_as_string, :value_as_concept_id,
    :unit_concept_id,
    :measurement_source_value, :unit_source_value, :value_source_value
)
"""

UPDATE_MEASUREMENT = """
UPDATE measurement SET
    measurement_datetime        = :measurement_datetime,
    measurement_time            = :measurement_time,
    measurement_type_concept_id = :measurement_type_concept_id,
    value_as_number             = :value_as_number,
    value_as_string             = :value_as_string,
    value_as_concept_id         = :value_as_concept_id,
    unit_concept_id             = :unit_concept_id,
    unit_source_value           = :unit_source_value,
    value_source_value          = :value_source_value
WHERE measurement_id = :measurement_id
"""

# --- drug_exposure ---------------------------------------------------------

NEXT_DRUG_EXPOSURE_ID = """
SELECT COALESCE(MAX(drug_exposure_id), 0) + 1 AS next_id FROM drug_exposure
"""

SELECT_DRUG_EXPOSURE = """
SELECT drug_exposure_id
FROM drug_exposure
WHERE person_id = :person_id
  AND drug_concept_id = :drug_concept_id
  AND drug_exposure_start_date = :drug_exposure_start_date
LIMIT 1
"""

INSERT_DRUG_EXPOSURE = """
INSERT INTO drug_exposure (
    drug_exposure_id, person_id, drug_concept_id,
    drug_exposure_start_date, drug_exposure_start_datetime,
    drug_exposure_end_date, drug_exposure_end_datetime,
    drug_type_concept_id,
    stop_reason, quantity, days_supply, sig,
    route_concept_id,
    drug_source_value, route_source_value, dose_unit_source_value
) VALUES (
    :drug_exposure_id, :person_id, :drug_concept_id,
    :drug_exposure_start_date, :drug_exposure_start_datetime,
    :drug_exposure_end_date, :drug_exposure_end_datetime,
    :drug_type_concept_id,
    :stop_reason, :quantity, :days_supply, :sig,
    :route_concept_id,
    :drug_source_value, :route_source_value, :dose_unit_source_value
)
"""

UPDATE_DRUG_EXPOSURE = """
UPDATE drug_exposure SET
    drug_exposure_start_datetime = :drug_exposure_start_datetime,
    drug_exposure_end_date       = :drug_exposure_end_date,
    drug_exposure_end_datetime   = :drug_exposure_end_datetime,
    drug_type_concept_id         = :drug_type_concept_id,
    stop_reason                  = :stop_reason,
    quantity                     = :quantity,
    days_supply                  = :days_supply,
    sig                          = :sig,
    route_concept_id             = :route_concept_id,
    drug_source_value            = :drug_source_value,
    route_source_value           = :route_source_value,
    dose_unit_source_value       = :dose_unit_source_value
WHERE drug_exposure_id = :drug_exposure_id
"""

# --- procedure_occurrence --------------------------------------------------

NEXT_PROCEDURE_ID = """
SELECT COALESCE(MAX(procedure_occurrence_id), 0) + 1 AS next_id FROM procedure_occurrence
"""

SELECT_PROCEDURE_OCCURRENCE = """
SELECT procedure_occurrence_id
FROM procedure_occurrence
WHERE person_id = :person_id
  AND procedure_concept_id = :procedure_concept_id
  AND procedure_date = :procedure_date
LIMIT 1
"""

INSERT_PROCEDURE_OCCURRENCE = """
INSERT INTO procedure_occurrence (
    procedure_occurrence_id, person_id, procedure_concept_id,
    procedure_date, procedure_datetime,
    procedure_end_date, procedure_end_datetime,
    procedure_type_concept_id,
    quantity,
    procedure_source_value, modifier_source_value
) VALUES (
    :procedure_occurrence_id, :person_id, :procedure_concept_id,
    :procedure_date, :procedure_datetime,
    :procedure_end_date, :procedure_end_datetime,
    :procedure_type_concept_id,
    :quantity,
    :procedure_source_value, :modifier_source_value
)
"""

UPDATE_PROCEDURE_OCCURRENCE = """
UPDATE procedure_occurrence SET
    procedure_datetime        = :procedure_datetime,
    procedure_end_date        = :procedure_end_date,
    procedure_end_datetime    = :procedure_end_datetime,
    procedure_type_concept_id = :procedure_type_concept_id,
    quantity                  = :quantity,
    procedure_source_value    = :procedure_source_value,
    modifier_source_value     = :modifier_source_value
WHERE procedure_occurrence_id = :procedure_occurrence_id
"""
