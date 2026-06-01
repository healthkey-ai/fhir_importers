"""Epic connector DRF views (ported from the FastAPI router).

All `/epic/*` endpoints require an authenticated platform identity — the
patient's forwarded Firebase JWT (integrated mode) or a local SimpleJWT
(standalone mode) resolved to an `accounts.Identity` by PartnerAuthentication.

Phase 0 scope: the auth handshake only. `finish` returns the Epic tokens to
the caller, exactly as the FastAPI service did. Phase 2 swaps this for
Connection persistence + a sync job.
"""
import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .organizations import UnknownOrganization
from .serializers import (
    FinishRequestSerializer,
    FinishResponseSerializer,
    OrganizationOutSerializer,
    StartRequestSerializer,
    StartResponseSerializer,
)
from .service import InvalidStateError
from .services import get_auth_service, get_organizations

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
            tokens = get_auth_service().finish(
                body.validated_data["code"], body.validated_data["state"]
            )
        except InvalidStateError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            FinishResponseSerializer(
                {
                    "access_token": tokens.access_token,
                    "refresh_token": tokens.refresh_token,
                    "id_token": tokens.id_token,
                    "expires_in": tokens.expires_in,
                    "scope": tokens.scope,
                    "patient": tokens.patient,
                }
            ).data
        )
