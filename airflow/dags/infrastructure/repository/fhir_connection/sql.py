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

# --- scheduler-only queries -------------------------------------------------

# Flag rows whose access_token will expire within :days days as expiring_soon.
# Only touch rows currently in `connected` — we don't want to "downgrade"
# rows the SmartTokenRefresher already flipped to needs_reauth.
FLAG_EXPIRING_TOKENS = """
UPDATE fhir_connection SET
    status = 'expiring_soon',
    updated_at = NOW()
WHERE status = 'connected'
  AND expires_at < NOW() + (:days || ' days')::interval
"""

# Connections due for incremental sync. Joined with fhir_institution so the
# scheduler can dispatch fhir_extract vs fhir_bulk_extract per row.
SELECT_DUE_FOR_SYNC = """
SELECT
    c.id AS connection_id,
    c.institution_id,
    i.slug AS institution_slug,
    i.supports_bulk_export,
    c.last_successful_sync
FROM fhir_connection c
JOIN fhir_institution i ON i.id = c.institution_id
WHERE c.status IN ('connected', 'expiring_soon')
  AND i.is_active
  AND (
        c.last_successful_sync IS NULL
        OR c.last_successful_sync < NOW() - (:min_age_hours || ' hours')::interval
      )
ORDER BY c.last_successful_sync ASC NULLS FIRST, c.id ASC
LIMIT :limit
"""
