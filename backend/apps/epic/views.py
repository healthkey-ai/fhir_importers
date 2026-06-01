"""Epic connector DRF views (ported from the FastAPI router).

All `/epic/*` endpoints require an authenticated platform identity — the
patient's forwarded Firebase JWT (integrated mode) or a local SimpleJWT
(standalone mode) resolved to an `accounts.Identity` by PartnerAuthentication.

Phase 0 scope: the auth handshake only. `finish` returns the Epic tokens to
the caller, exactly as the FastAPI service did. Phase 2 swaps this for
Connection persistence + a sync job.
"""
import logging
from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Connection, SyncJob
from .organizations import UnknownOrganization
from .serializers import (
    ConnectionSerializer,
    FinishRequestSerializer,
    FinishResponseSerializer,
    OrganizationOutSerializer,
    StartRequestSerializer,
    StartResponseSerializer,
    SyncJobSerializer,
)
from .service import InvalidStateError
from .services import get_auth_service, get_organizations
from .tasks import run_sync_task

logger = logging.getLogger(__name__)


class HealthView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class OrganizationsView(APIView):
    def get(self, request):
        orgs = get_organizations().list()
        data = OrganizationOutSerializer(
            [{"alias": o.alias, "title": o.title, "endpoint_url": o.endpoint_url} for o in orgs],
            many=True,
        ).data
        return Response(data)


class AuthStartView(APIView):
    def post(self, request):
        body = StartRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            result = get_auth_service().start(body.validated_data["organization_alias"])
        except UnknownOrganization:
            return Response(
                {"detail": f"Unknown organization alias: {body.validated_data['organization_alias']}"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            StartResponseSerializer(
                {"authorization_url": result.authorization_url, "state": result.state}
            ).data
        )


class AuthFinishView(APIView):
    def post(self, request):
        body = FinishRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            tokens, org_alias = get_auth_service().finish(
                body.validated_data["code"], body.validated_data["state"]
            )
        except InvalidStateError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Persist the connection (tokens encrypted) for the authenticated
        # identity — they are NOT returned to the browser. One connection per
        # (identity, org); re-connecting refreshes the stored tokens.
        connection, _ = Connection.objects.get_or_create(
            identity=request.user, org_alias=org_alias,
        )
        connection.access_token = tokens.access_token
        connection.refresh_token = tokens.refresh_token or ""
        connection.scope = tokens.scope or ""
        connection.epic_patient_id = tokens.patient or ""
        connection.token_expires_at = timezone.now() + timedelta(seconds=tokens.expires_in)
        connection.save()

        job = SyncJob.objects.create(connection=connection)
        run_sync_task.delay(job.id)

        return Response(
            FinishResponseSerializer(
                {
                    "connection_id": connection.id,
                    "sync_job_id": job.id,
                    "organization_alias": org_alias,
                    "expires_in": tokens.expires_in,
                    "scope": tokens.scope,
                    "patient": tokens.patient,
                }
            ).data
        )


class ConnectionsView(APIView):
    """GET /epic/connections — the caller's own MyChart connections."""

    def get(self, request):
        conns = Connection.objects.filter(identity=request.user).order_by("-created_at")
        return Response(ConnectionSerializer(conns, many=True).data)


class ConnectionSyncView(APIView):
    """POST /epic/connections/{id}/sync — re-run sync for one connection."""

    def post(self, request, connection_id):
        connection = get_object_or_404(
            Connection, id=connection_id, identity=request.user,
        )
        job = SyncJob.objects.create(connection=connection)
        run_sync_task.delay(job.id)
        return Response(SyncJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class SyncJobView(APIView):
    """GET /epic/sync/{job_id} — poll a sync job (own connections only)."""

    def get(self, request, job_id):
        job = get_object_or_404(
            SyncJob, id=job_id, connection__identity=request.user,
        )
        return Response(SyncJobSerializer(job).data)
