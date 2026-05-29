import os

import firebase_admin
from fastapi import Header, HTTPException, status
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

from .config import get_settings

_initialized = False


def _ensure_firebase_app() -> None:
    global _initialized
    if _initialized:
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
    _initialized = True


async def get_current_user_uid(authorization: str = Header(default="")) -> str:
    """Verify the `Authorization: Bearer <firebase-id-token>` and return the UID."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization[len("Bearer "):]
    _ensure_firebase_app()
    try:
        decoded = firebase_auth.verify_id_token(token, check_revoked=False)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    uid = decoded.get("uid")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing uid")
    return uid
