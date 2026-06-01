import logging

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Identity
from .serializers import IdentitySerializer, RegisterSerializer

logger = logging.getLogger(__name__)


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login with email+password for local identities."""
    username_field = "email"

    def validate(self, attrs):
        email = attrs.get("email", "")
        password = attrs.get("password", "")

        try:
            identity = Identity.objects.get(issuer="urn:local", email=email)
        except Identity.DoesNotExist:
            from rest_framework_simplejwt.exceptions import AuthenticationFailed
            raise AuthenticationFailed("No active account found with the given credentials")

        if not identity.check_password(password):
            from rest_framework_simplejwt.exceptions import AuthenticationFailed
            raise AuthenticationFailed("No active account found with the given credentials")

        if not identity.is_active:
            from rest_framework_simplejwt.exceptions import AuthenticationFailed
            raise AuthenticationFailed("No active account found with the given credentials")

        refresh = self.get_token(identity)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class RegisterView(APIView):
    """
    POST /api/v1/auth/register/
    Body: { "email": "...", "password": "..." }
    Response: { "user": {...}, "tokens": { "access": "...", "refresh": "..." } }
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identity = serializer.save()

        refresh = RefreshToken.for_user(identity)
        return Response(
            {
                "user": IdentitySerializer(identity).data,
                "tokens": {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class MeView(generics.RetrieveAPIView):
    """
    GET /api/v1/auth/me/
    Returns the currently authenticated identity.
    """

    serializer_class = IdentitySerializer

    def get_object(self):
        return self.request.user


class PartnerTokenView(APIView):
    """Exchange a partner token for PHR JWT credentials.

    Accepts any token recognised by the configured PARTNER_AUTH_PROVIDERS
    (Firebase, external JWT, etc.) and returns a PHR access + refresh pair.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from .providers import get_providers
        from .providers.base import decode_jwt_unverified
        from .partner_auth import PartnerAuthentication

        token = request.data.get("token", "") or request.data.get("firebase_token", "")
        if not token:
            return Response(
                {"detail": "token required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        providers = get_providers()
        unverified = decode_jwt_unverified(token)
        identity = None
        for provider in providers:
            if not provider.can_handle(token, unverified):
                continue
            claims = provider.verify(token)
            if claims is None:
                continue
            identity = PartnerAuthentication._get_or_create_identity(claims)
            break

        if identity is None:
            return Response(
                {"detail": "Token not recognised by any configured provider"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(identity)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user_id": identity.pk,
        })
