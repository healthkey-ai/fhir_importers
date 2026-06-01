"""DRF serializers for the Epic connector API (ported from FastAPI schemas)."""
from rest_framework import serializers


class OrganizationOutSerializer(serializers.Serializer):
    alias = serializers.CharField()
    title = serializers.CharField()
    endpoint_url = serializers.CharField()


class StartRequestSerializer(serializers.Serializer):
    organization_alias = serializers.CharField(
        help_text="Alias of an organization registered in organizations.json",
    )


class StartResponseSerializer(serializers.Serializer):
    authorization_url = serializers.CharField()
    state = serializers.CharField()


class FinishRequestSerializer(serializers.Serializer):
    code = serializers.CharField()
    state = serializers.CharField()


class FinishResponseSerializer(serializers.Serializer):
    """Phase 2: tokens are persisted server-side (encrypted), never returned to
    the browser. The caller gets the connection + the kicked-off sync job."""
    connection_id = serializers.IntegerField()
    sync_job_id = serializers.IntegerField()
    organization_alias = serializers.CharField()
    expires_in = serializers.IntegerField()
    scope = serializers.CharField(allow_null=True, required=False)
    patient = serializers.CharField(
        allow_null=True, required=False,
        help_text="SMART-on-FHIR patient launch context, if returned",
    )


class SyncJobSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    connection_id = serializers.IntegerField()
    status = serializers.CharField()
    resources_fetched = serializers.IntegerField()
    created_count = serializers.IntegerField()
    counts = serializers.JSONField()
    person_id = serializers.IntegerField(allow_null=True)
    error = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)


class ConnectionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    org_alias = serializers.CharField()
    epic_patient_id = serializers.CharField(allow_blank=True)
    scope = serializers.CharField(allow_blank=True)
    token_expires_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    last_sync = serializers.SerializerMethodField()
    total_records = serializers.SerializerMethodField()

    def get_last_sync(self, obj):
        job = obj.sync_jobs.order_by("-created_at").first()
        if job is None:
            return None
        return SyncJobSerializer(job).data

    def get_total_records(self, obj):
        # Records imported overall (created_count is new-per-sync, so re-syncs
        # add 0 — the sum is the cumulative imported total).
        from django.db.models import Sum
        return obj.sync_jobs.filter(status="succeeded").aggregate(
            t=Sum("created_count"))["t"] or 0
