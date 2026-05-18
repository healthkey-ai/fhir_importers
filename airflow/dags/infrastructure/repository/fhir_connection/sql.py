_COLUMNS = """
    id, person_id, institution_id, organization_id,
    access_token_encrypted, refresh_token_encrypted,
    expires_at, scope_granted,
    fhir_patient_id, status,
    last_successful_sync, last_attempted_sync, last_token_refresh_at,
    failure_count, last_error,
    created_at, updated_at
"""

SELECT_BY_ID = f"SELECT {_COLUMNS} FROM fhir_connection WHERE id = :id"

SELECT_FOR_UPDATE = f"SELECT {_COLUMNS} FROM fhir_connection WHERE id = :id FOR UPDATE"

UPDATE_TOKENS = """
UPDATE fhir_connection SET
    access_token_encrypted = :access_token_encrypted,
    refresh_token_encrypted = :refresh_token_encrypted,
    expires_at = :expires_at,
    status = :status,
    last_token_refresh_at = :last_token_refresh_at,
    last_error = :last_error,
    updated_at = NOW()
WHERE id = :id
"""

MARK_NEEDS_REAUTH = """
UPDATE fhir_connection SET
    status = 'needs_reauth',
    last_error = :reason,
    updated_at = NOW()
WHERE institution_id = :institution_id
  AND status IN ('connected', 'expiring_soon', 'degraded')
"""

RECORD_SYNC_SUCCESS = """
UPDATE fhir_connection SET
    last_attempted_sync = :attempted_at,
    last_successful_sync = :attempted_at,
    failure_count = 0,
    last_error = '',
    updated_at = NOW()
WHERE id = :id
"""

RECORD_SYNC_FAILURE = """
UPDATE fhir_connection SET
    last_attempted_sync = :attempted_at,
    failure_count = failure_count + 1,
    last_error = :error,
    updated_at = NOW()
WHERE id = :id
"""
