"""SQL for the `provenance_record` table (Django generic FK)."""

SELECT_CONTENT_TYPE_ID = """
SELECT id FROM django_content_type
WHERE app_label = :app_label AND model = :model
LIMIT 1
"""

INSERT_PROVENANCE_RECORD = """
INSERT INTO provenance_record (
    source,
    source_user_id,
    target_patient_id,
    modification_reason,
    organization_id,
    content_type_id,
    object_id,
    created_at
) VALUES (
    :source,
    :source_user_id,
    :target_patient_id,
    :modification_reason,
    :organization_id,
    :content_type_id,
    :object_id,
    NOW()
)
RETURNING id
"""
