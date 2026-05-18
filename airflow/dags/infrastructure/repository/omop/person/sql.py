"""SQL for the Person + PatientInfo repository.

Targets the Django-owned OMOP schema in ctomop:
    person          (PK: person_id; not auto-generated)
    patient_info    (PK: id; UNIQUE: person_id)
"""

# --- person ---------------------------------------------------------------

SELECT_PERSON_BY_NAME_AND_BIRTH_YEAR = """
SELECT
    person_id,
    gender_concept_id,
    gender_source_value,
    year_of_birth,
    month_of_birth,
    day_of_birth,
    birth_datetime,
    ethnicity_concept_id,
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

NEXT_PERSON_ID = """
SELECT COALESCE(MAX(person_id), 999) + 1 AS next_id FROM person
"""

INSERT_PERSON = """
INSERT INTO person (
    person_id,
    gender_concept_id,
    gender_source_value,
    year_of_birth,
    month_of_birth,
    day_of_birth,
    birth_datetime,
    ethnicity_concept_id,
    location_id,
    given_name,
    family_name
) VALUES (
    :person_id,
    :gender_concept_id,
    :gender_source_value,
    :year_of_birth,
    :month_of_birth,
    :day_of_birth,
    :birth_datetime,
    :ethnicity_concept_id,
    :location_id,
    :given_name,
    :family_name
)
"""

UPDATE_PERSON_BY_ID = """
UPDATE person SET
    gender_concept_id    = :gender_concept_id,
    gender_source_value  = :gender_source_value,
    year_of_birth        = :year_of_birth,
    month_of_birth       = :month_of_birth,
    day_of_birth         = :day_of_birth,
    birth_datetime       = :birth_datetime,
    ethnicity_concept_id = :ethnicity_concept_id,
    location_id          = :location_id,
    given_name           = :given_name,
    family_name          = :family_name
WHERE person_id = :person_id
"""

# --- patient_info ---------------------------------------------------------

SELECT_PATIENT_INFO_BY_PERSON_ID = """
SELECT id, person_id, organization_id
FROM patient_info
WHERE person_id = :person_id
LIMIT 1
"""

# Dynamic INSERT ... ON CONFLICT (person_id) DO UPDATE for arbitrary patch columns.
# Template — caller fills in `cols`, `placeholders`, and `update_assignments`.
UPSERT_PATIENT_INFO_TEMPLATE = """
INSERT INTO patient_info (person_id, organization_id, created_at, updated_at, {cols})
VALUES (:person_id, :organization_id, NOW(), NOW(), {placeholders})
ON CONFLICT (person_id) DO UPDATE SET
    organization_id = COALESCE(EXCLUDED.organization_id, patient_info.organization_id),
    updated_at = NOW(),
    {update_assignments}
RETURNING id
"""

# Used when the patch is empty but we still need a row to exist (e.g. to
# attach an organization_id or just to anchor a provenance record).
UPSERT_PATIENT_INFO_EMPTY = """
INSERT INTO patient_info (person_id, organization_id, created_at, updated_at)
VALUES (:person_id, :organization_id, NOW(), NOW())
ON CONFLICT (person_id) DO UPDATE SET
    organization_id = COALESCE(EXCLUDED.organization_id, patient_info.organization_id),
    updated_at = NOW()
RETURNING id
"""
