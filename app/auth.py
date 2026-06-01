import abc
import os

import firebase_admin
from fastapi import Header, HTTPException, Request, status
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

from .config import get_settings


class BaseTokenVerifier(abc.ABC):
    """Verify a bearer token; return uid or raise HTTPException(401)."""

    @abc.abstractmethod
    async def verify(self, token: str) -> str: ...


class FirebaseTokenVerifier(BaseTokenVerifier):
    def __init__(self) -> None:
        self._initialized = False

    def _ensure_firebase_app(self) -> None:
        if self._initialized:
            return
        settings = get_settings()
        options = {"projectId": settings.firebase_project_id} if settings.firebase_project_id else {}

        if settings.firebase_credentials_path:
            cred = credentials.Certificate(settings.firebase_credentials_path)
        elif os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
            # Emulator tokens are unsigned; firebase-admin skips signature checks
            # when FIREBASE_AUTH_EMULATOR_HOST is set. No real credential needed.
            class _EmulatorCredential(credentials.Base):
                def get_credential(self):
                    return None

            cred = _EmulatorCredential()
        else:
            cred = credentials.ApplicationDefault()

        try:
            firebase_admin.initialize_app(cred, options)
        except ValueError:
            pass  # already initialized
        self._initialized = True

    async def verify(self, token: str) -> str:
        self._ensure_firebase_app()
        try:
            decoded = firebase_auth.verify_id_token(token, check_revoked=False)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        uid = decoded.get("uid")
        if not uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing uid",
            )
        return uid


async def get_current_user_uid(
    request: Request,
    authorization: str = Header(default=""),
) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = authorization[len("Bearer ") :]
    verifier: BaseTokenVerifier = request.app.state.token_verifier
    return await verifier.verify(token)
