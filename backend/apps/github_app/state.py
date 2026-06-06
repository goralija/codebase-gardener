import secrets
from collections.abc import MutableMapping
from typing import Any

from django.core import signing
from django.utils import timezone
from django.utils.crypto import constant_time_compare


INSTALL_STATE_MAX_AGE_SECONDS = 600
INSTALL_STATE_PURPOSE = "github_app_install"
INSTALL_STATE_SALT = "github-app-install-state"
INSTALL_STATE_SESSION_KEY = "github_app_install_state_nonce"


def create_install_state(
    session: MutableMapping[str, Any] | None = None,
) -> str:
    nonce = secrets.token_urlsafe(32)
    payload = {
        "purpose": INSTALL_STATE_PURPOSE,
        "issued_at": timezone.now().isoformat(),
    }
    if session is not None:
        session[INSTALL_STATE_SESSION_KEY] = nonce
        payload["nonce"] = nonce

    return signing.dumps(
        payload,
        salt=INSTALL_STATE_SALT,
        compress=True,
    )


def load_install_state(
    state: str,
    *,
    session: MutableMapping[str, Any] | None = None,
    consume: bool = False,
) -> dict[str, Any]:
    payload = signing.loads(
        state,
        max_age=INSTALL_STATE_MAX_AGE_SECONDS,
        salt=INSTALL_STATE_SALT,
    )
    if payload.get("purpose") != INSTALL_STATE_PURPOSE:
        raise signing.BadSignature("Invalid install state purpose.")
    if session is not None:
        _validate_session_nonce(payload, session)
        if consume:
            session.pop(INSTALL_STATE_SESSION_KEY, None)
    return payload


def _validate_session_nonce(
    payload: dict[str, Any],
    session: MutableMapping[str, Any],
) -> None:
    state_nonce = payload.get("nonce")
    session_nonce = session.get(INSTALL_STATE_SESSION_KEY)
    if not isinstance(state_nonce, str) or not isinstance(session_nonce, str):
        raise signing.BadSignature("Install state was not bound to this session.")
    if not constant_time_compare(state_nonce, session_nonce):
        raise signing.BadSignature("Install state session nonce did not match.")
