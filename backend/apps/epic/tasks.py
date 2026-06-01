"""Background sync: connector → ctomop.

Phase 2 proves the identity-resolved ingest path using a SAMPLE bundle. Phase 3
replaces _build_bundle() with a real Epic FHIR fetch (EpicFhirClient) using the
Connection's stored token.
"""
import logging

from celery import shared_task
from django.utils import timezone

from . import ctomop_client
from .models import Connection, SyncJob

logger = logging.getLogger(__name__)


def _sample_bundle(connection: Connection) -> dict:
    """Placeholder FHIR R4 Bundle until Epic fetch lands in Phase 3."""
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"resource": {
                "resourceType": "Patient",
                "id": connection.epic_patient_id or "sample",
                "name": [{"family": "Sample", "given": ["Connected"]}],
                "birthDate": "1980-01-01",
                "gender": "unknown",
            }},
            {"resource": {
                "resourceType": "Observation",
                "code": {"coding": [{"system": "http://loinc.org", "code": "718-7",
                                     "display": "Hemoglobin"}]},
                "effectiveDateTime": "2026-05-01",
                "valueQuantity": {"value": 13.5, "unit": "g/dL"},
            }},
        ],
    }


def _build_bundle(connection: Connection) -> dict:
    # Phase 3: fetch from Epic with EpicFhirClient(connection.access_token).
    return _sample_bundle(connection)


def run_sync(job_id: int) -> None:
    """Execute a SyncJob: build a bundle and post it to ctomop."""
    job = SyncJob.objects.select_related("connection", "connection__identity").get(pk=job_id)
    job.status = SyncJob.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])

    conn = job.connection
    identity = conn.identity
    try:
        bundle = _build_bundle(conn)
        result = ctomop_client.sync_fhir_bundle(
            bundle=bundle,
            actor_iss=identity.issuer,
            actor_sub=identity.sub,
        )
        job.status = SyncJob.SUCCEEDED
        job.resources_fetched = len(bundle.get("entry", []))
        job.created_count = result.created_count
        job.person_id = result.person_id
    except Exception as exc:  # noqa: BLE001 — record any failure on the job
        logger.exception("SyncJob %s failed", job_id)
        job.status = SyncJob.FAILED
        job.error = str(exc)[:2000]
    finally:
        job.finished_at = timezone.now()
        job.save()


@shared_task
def run_sync_task(job_id: int) -> None:
    run_sync(job_id)
