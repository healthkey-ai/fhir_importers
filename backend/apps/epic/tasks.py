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


def run_sync(job_id: int) -> None:
    """Execute a SyncJob: fetch the Epic bundle and post it to ctomop."""
    job = SyncJob.objects.select_related("connection", "connection__identity").get(pk=job_id)
    job.status = SyncJob.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])

    conn = job.connection
    identity = conn.identity
    try:
        bundle = build_bundle_for_connection(conn)
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
