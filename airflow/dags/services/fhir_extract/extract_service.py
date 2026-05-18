"""Orchestrator: connection_id → fresh tokens → FHIR Bundle → S3 artifact.

The Airflow `fhir_extract` DAG calls this service once per run. It owns
the high-level sequence; HTTP details live in `paginated_extractor`,
locking + token refresh live in the `oauth` package and the connection
repository.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import StrEnum

from entities.fhir.connection import FhirConnection
from entities.fhir.institution import Institution
from infrastructure.oauth import NeedsReauth, SmartRefreshError, SmartTokenRefresher
from infrastructure.repository.fhir_connection import FhirConnectionRepository
from infrastructure.repository.institution import InstitutionRepository
from services.artifact import ArtifactKey, ArtifactService
from services.fhir_extract.bulk_exporter import (
    download_manifest_as_bundle,
    initiate_export,
    poll_until_complete,
)
from services.fhir_extract.paginated_extractor import fetch_patient_everything

_logger = logging.getLogger(__name__)


class SyncMode(StrEnum):
    INITIAL = "initial"
    INCREMENTAL = "incremental"


class FhirExtractError(Exception):
    """Top-level wrapper raised by FhirExtractService."""


class FhirExtractService:
    """Pulls a patient's FHIR Bundle from an institution and lands it in S3."""

    def __init__(
        self,
        connection_repository: FhirConnectionRepository,
        institution_repository: InstitutionRepository,
        token_refresher: SmartTokenRefresher,
        artifact_service: ArtifactService,
    ):
        self._connections = connection_repository
        self._institutions = institution_repository
        self._refresher = token_refresher
        self._artifacts = artifact_service

    def bulk_extract(
        self,
        *,
        connection_id: int,
        mode: SyncMode,
        artifact_key: ArtifactKey,
        resource_types: list[str] | None = None,
        poll_timeout_seconds: int = 60 * 60,
    ) -> ArtifactKey:
        """Pull via FHIR `$export` (initiate → poll → download manifest).

        Used by the `fhir_bulk_extract` DAG. Same return shape as `extract`:
        an artifact key whose contents are a Bundle dict ready for ingest.
        """
        attempted_at = datetime.now(tz=timezone.utc)
        try:
            connection, tokens = self._refresher.fresh_tokens_for(connection_id)
            institution = self._require_institution(connection)
            if not institution.supports_bulk_export:
                raise FhirExtractError(
                    f"Institution {institution.slug} is not configured for $export "
                    "(set supports_bulk_export=True on the fhir_institution row)."
                )
            if not connection.fhir_patient_id:
                raise FhirExtractError(
                    f"Connection {connection_id} has no fhir_patient_id."
                )
            since = self._since_watermark(connection, mode)

            _logger.info(
                "Bulk export institution=%s patient=%s mode=%s types=%s",
                institution.slug, connection.fhir_patient_id, mode.value, resource_types,
            )

            status_url = initiate_export(
                institution=institution,
                fhir_patient_id=connection.fhir_patient_id,
                access_token=tokens.access_token,
                since=since,
                resource_types=resource_types,
            )
            manifest = poll_until_complete(
                institution=institution,
                status_url=status_url,
                access_token=tokens.access_token,
                poll_timeout_seconds=poll_timeout_seconds,
            )
            bundle = download_manifest_as_bundle(
                institution=institution,
                manifest=manifest,
                access_token=tokens.access_token,
            )
            self._artifacts.upload_json(artifact_key, bundle)

            self._connections.record_sync_attempt(
                connection_id, succeeded=True, attempted_at=attempted_at,
            )
            _logger.info(
                "Bulk extract done institution=%s patient=%s entries=%d",
                institution.slug, connection.fhir_patient_id, bundle["total"],
            )
            return artifact_key

        except NeedsReauth as e:
            self._connections.record_sync_attempt(
                connection_id, succeeded=False, attempted_at=attempted_at,
                error=f"needs_reauth: {e}",
            )
            raise
        except SmartRefreshError as e:
            self._connections.record_sync_attempt(
                connection_id, succeeded=False, attempted_at=attempted_at,
                error=f"refresh failed: {e}",
            )
            raise FhirExtractError(str(e)) from e
        except Exception as e:
            self._connections.record_sync_attempt(
                connection_id, succeeded=False, attempted_at=attempted_at,
                error=str(e)[:500],
            )
            raise

    def extract(
        self,
        *,
        connection_id: int,
        mode: SyncMode,
        artifact_key: ArtifactKey,
    ) -> ArtifactKey:
        """Pull the bundle for `connection_id` and upload as JSON at
        `artifact_key`. Returns the same key for convenience."""
        attempted_at = datetime.now(tz=timezone.utc)
        try:
            connection, tokens = self._refresher.fresh_tokens_for(connection_id)
            institution = self._require_institution(connection)
            since = self._since_watermark(connection, mode)

            if not connection.fhir_patient_id:
                raise FhirExtractError(
                    f"Connection {connection_id} has no fhir_patient_id — initial OAuth "
                    "must have failed to capture it."
                )

            _logger.info(
                "Extracting institution=%s patient=%s mode=%s since=%s",
                institution.slug, connection.fhir_patient_id, mode.value, since,
            )

            bundle = fetch_patient_everything(
                institution=institution,
                fhir_patient_id=connection.fhir_patient_id,
                access_token=tokens.access_token,
                since=since,
            )
            self._artifacts.upload_json(artifact_key, bundle)

            self._connections.record_sync_attempt(
                connection_id,
                succeeded=True,
                attempted_at=attempted_at,
            )
            _logger.info(
                "Extract done institution=%s patient=%s entries=%d",
                institution.slug, connection.fhir_patient_id, bundle.get("total", 0),
            )
            return artifact_key

        except NeedsReauth as e:
            self._connections.record_sync_attempt(
                connection_id,
                succeeded=False,
                attempted_at=attempted_at,
                error=f"needs_reauth: {e}",
            )
            raise
        except SmartRefreshError as e:
            self._connections.record_sync_attempt(
                connection_id,
                succeeded=False,
                attempted_at=attempted_at,
                error=f"refresh failed: {e}",
            )
            raise FhirExtractError(str(e)) from e
        except Exception as e:
            self._connections.record_sync_attempt(
                connection_id,
                succeeded=False,
                attempted_at=attempted_at,
                error=str(e)[:500],
            )
            raise

    def _require_institution(self, connection: FhirConnection) -> Institution:
        if connection.institution_id is None:
            raise FhirExtractError(
                f"Connection {connection.id} has no institution_id"
            )
        institution = self._institutions.get_by_id(connection.institution_id)
        if institution is None:
            raise FhirExtractError(
                f"Institution {connection.institution_id} not found"
            )
        return institution

    @staticmethod
    def _since_watermark(connection: FhirConnection, mode: SyncMode) -> str | None:
        if mode != SyncMode.INCREMENTAL:
            return None
        watermark = connection.last_successful_sync
        return watermark.isoformat() if watermark else None
