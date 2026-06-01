"""Connector persistence: a patient's Epic connection + its sync jobs.

Like hk-labs' UploadJob.user → Identity, Connection links to the shared
(issuer, sub) Identity. The connector stores Epic tokens (encrypted) but
NEVER a ctomop person_id — ctomop owns the identity↔Person link.
"""
from django.conf import settings
from django.db import models

from . import crypto


class Connection(models.Model):
    """A patient's authenticated link to one Epic/MyChart organization."""

    identity = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="mychart_connections",
    )
    org_alias = models.CharField(max_length=255)
    # SMART launch context patient id from Epic (provenance/dedup, NOT the
    # person key — identity is). Optional.
    epic_patient_id = models.CharField(max_length=255, blank=True, default="")

    # Encrypted at rest (Fernet). Use the *_token properties, not these columns.
    access_token_enc = models.TextField(blank=True, default="")
    refresh_token_enc = models.TextField(blank=True, default="")
    token_expires_at = models.DateTimeField(null=True, blank=True)
    scope = models.CharField(max_length=512, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "epic_connection"
        constraints = [
            models.UniqueConstraint(
                fields=["identity", "org_alias"],
                name="uq_connection_identity_org",
            ),
        ]

    # --- token accessors (transparent encryption) ---
    @property
    def access_token(self) -> str:
        return crypto.decrypt(self.access_token_enc)

    @access_token.setter
    def access_token(self, value: str):
        self.access_token_enc = crypto.encrypt(value or "")

    @property
    def refresh_token(self) -> str:
        return crypto.decrypt(self.refresh_token_enc)

    @refresh_token.setter
    def refresh_token(self, value: str):
        self.refresh_token_enc = crypto.encrypt(value or "")

    def __str__(self):
        return f"Connection(identity={self.identity_id}, org={self.org_alias})"


class SyncJob(models.Model):
    """One FHIR fetch → ctomop ingest run for a Connection."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STATUS_CHOICES = [
        (QUEUED, "Queued"),
        (RUNNING, "Running"),
        (SUCCEEDED, "Succeeded"),
        (FAILED, "Failed"),
    ]

    connection = models.ForeignKey(
        Connection, on_delete=models.CASCADE, related_name="sync_jobs",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=QUEUED)
    resources_fetched = models.IntegerField(default=0)
    created_count = models.IntegerField(default=0)
    # Per-category breakdown CREATED this sync, updated live as chunks complete:
    # {"demographics": 0|1, "measurements": N, "conditions": N, "medications": N}
    counts = models.JSONField(default=dict, blank=True)
    # Person's CURRENT record totals on ctomop after this sync (records on file):
    # {"measurements": N, "conditions": N, "medications": N}
    record_totals = models.JSONField(default=dict, blank=True)
    # person_id is returned by ctomop for reconciliation; the connector does not
    # treat it as the identity key.
    person_id = models.BigIntegerField(null=True, blank=True)
    error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "epic_sync_job"
        ordering = ["-created_at"]

    def __str__(self):
        return f"SyncJob(id={self.pk}, status={self.status})"
