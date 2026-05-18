_COLUMNS = """
    id, slug, display_name,
    fhir_base, smart_config_url, client_id, scopes, redirect_uri,
    jwks_kid,
    supports_bulk_export,
    base_backoff_seconds, max_backoff_seconds, max_retry_count,
    respect_retry_after, jitter_factor, retryable_status_codes,
    daily_quota_reset_utc_hour,
    is_active, created_at, updated_at
"""

SELECT_BY_ID = f"SELECT {_COLUMNS} FROM fhir_institution WHERE id = :id"

SELECT_BY_SLUG = f"SELECT {_COLUMNS} FROM fhir_institution WHERE slug = :slug"
