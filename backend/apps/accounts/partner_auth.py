"""DRF authentication backend that delegates to pluggable token providers.

Iterates over PARTNER_AUTH_PROVIDERS in order.  Each provider first gets
a lightweight ``can_handle()`` check (unverified JWT payload inspection —
no secrets, no external calls) before the real ``verify()`` is invoked.

Verified results are cached in-memory for up to 60s to avoid repeated
network round-trips (e.g. Firebase revocation checks) on every request.
"""
from __future__ import annotations

import hashlib
import logging
import time
import traceback

from django.conf import settings
from rest_framework.authentication import BaseAuthentication

from .models import Identity
from .providers import get_providers
from .providers.base import TokenClaims, decode_jwt_unverified

logger = logging.getLogger(__name__)

_AUTH_CACHE_TTL = getattr(settings, "PARTNER_AUTH_CACHE_TTL", 60)
_auth_cache: dict[str, tuple[float, Identity, TokenClaims]] = {}
_CACHE_MAX_SIZE = 256


def _cache_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:32]


def _cache_get(token: str) -> tuple[Identity, TokenClaims] | None:
    key = _cache_key(token)
    entry = _auth_cache.get(key)
    if entry is None:
        return None
    ts, identity, claims = entry
    if time.monotonic() - ts > _AUTH_CACHE_TTL:
        del _auth_cache[key]
        return None
    return identity, claims


def _cache_set(token: str, identity: Identity, claims: TokenClaims) -> None:
    if len(_auth_cache) >= _CACHE_MAX_SIZE:
        cutoff = time.monotonic() - _AUTH_CACHE_TTL
        stale = [k for k, (ts, _, _) in _auth_cache.items() if ts < cutoff]
        for k in stale:
            del _auth_cache[k]
        if len(_auth_cache) >= _CACHE_MAX_SIZE:
            _auth_cache.clear()
    _auth_cache[_cache_key(token)] = (time.monotonic(), identity, claims)


class PartnerAuthentication(BaseAuthentication):

    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.startswith("Bearer "):
            logger.debug("partner_auth: no Bearer token")
            return None

        token = header[7:]

        cached = _cache_get(token)
        if cached is not None:
            return cached

        providers = get_providers()
        if not providers:
            logger.warning("partner_auth: no providers configured")
            return None

        unverified = decode_jwt_unverified(token)
        logger.info(
            "partner_auth: iss=%s sub=%s",
            (unverified or {}).get("iss", "?"),
            (unverified or {}).get("sub", "?"),
        )

        for provider in providers:
            if not provider.can_handle(token, unverified):
                continue

            try:
                claims = provider.verify(token)
            except Exception as exc:
                logger.error(
                    "partner_auth: %s.verify raised %s: %s\n%s",
                    type(provider).__name__, type(exc).__name__, exc,
                    traceback.format_exc(),
                )
                raise

            if claims is None:
                logger.warning("partner_auth: %s.verify returned None", type(provider).__name__)
                continue

            identity = self._get_or_create_identity(claims)
            logger.info(
                "partner_auth: authenticated identity=%s (id=%s) via %s",
                identity, identity.pk, type(provider).__name__,
            )
            _cache_set(token, identity, claims)
            return (identity, claims)

        logger.warning("partner_auth: no provider handled the token")
        return None

    @staticmethod
    def _get_or_create_identity(claims: TokenClaims) -> Identity:
        identity, created = Identity.objects.get_or_create_from_claims(claims)
        if created:
            identity.set_unusable_password()
            identity.save(update_fields=["password"])
            logger.info(
                "partner_auth: provisioned identity %d (%s|%s)",
                identity.pk, claims.issuer, claims.sub,
            )
        return identity
