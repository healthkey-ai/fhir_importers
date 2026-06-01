"""Background sync: connector → ctomop.

Fetches the patient's FHIR compartment from Epic (using the Connection's stored
token, refreshing if needed) and posts it to ctomop's identity-resolved
/api/fhir/sync/.
"""
import logging

from celery import shared_task
from django.utils import timezone

from . import ctomop_client
from .fetch import build_bundle_for_connection
from .models import SyncJob

logger = logging.getLogger(__name__)

# Post the compartment to ctomop in chunks so each request is small + fast
# (stays well under ctomop's 1000-entry bundle limit, no long-held request).
CHUNK_SIZE = 400


def _chunks(entries, size):
    for i in range(0, len(entries), size):
        yield entries[i:i + size]


def run_sync(job_id: int) -> None:
    """Execute a SyncJob: fetch the Epic compartment and post it to ctomop in chunks."""
    job = SyncJob.objects.select_related("connection", "connection__identity").get(pk=job_id)
    job.status = SyncJob.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])

    conn = job.connection
    identity = conn.identity
    try:
        bundle = build_bundle_for_connection(conn)
        entries = bundle.get("entry", []) or []

        created = 0
        person_id = None
        for chunk in _chunks(entries, CHUNK_SIZE):
            result = ctomop_client.sync_fhir_bundle(
                bundle={"resourceType": "Bundle", "type": "collection", "entry": chunk},
                actor_iss=identity.issuer,
                actor_sub=identity.sub,
            )
            created += result.created_count
            person_id = result.person_id or person_id

        job.status = SyncJob.SUCCEEDED
        job.resources_fetched = len(entries)
        job.created_count = created
        job.person_id = person_id
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
