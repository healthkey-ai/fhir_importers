"""Unit coverage for `HealthExClient.get_consent_state`.

Exercises the real HTTP + JSON-parse path — no autospec — using
`httpx.MockTransport` to feed canned responses. Verifies the
three-state dispatch that `poll_status` depends on for revocation
detection (see app/healthex_routers.py:167).

Endpoint under test: https://docs.healthex.io/api/get-patient-consents
"""
import json
import time

import httpx
import pytest

from services.healthex_client import HealthExClient, HealthExError


PROJECT_ID = "2f1c41d6-3752-4e30-b3ca-be78b8c828da"
EXTERNAL_ID = "o8UiBa79IpRqgWuYtzHjmEwJf3j1"
PATIENT_ID = "52a4f0f2-422e-4160-8350-096fcced82a8"


def _build_client(handler) -> HealthExClient:
    """HealthExClient with a MockTransport and a pre-cached org JWT.

    Pre-caching skips the /v1/auth/token round-trip so the mock only
    needs to cover the endpoint under test.
    """
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, base_url="https://healthex.test")
    client = HealthExClient(
        http=http,
        base_url="https://healthex.test",
        project_id=PROJECT_ID,
        api_key="test-key",
        api_secret="test-secret",
    )
    # Skip token mint — cache a fake token good for an hour.
    client._cached_token = "fake-jwt"
    client._cached_until = time.time() + 3600
    return client


def _consents_response(entries: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"results": entries})


# ---------------------------------------------------------------------- #
# Case 1: OPTED_IN — returns the patient_id, known_by_healthex=True      #
# ---------------------------------------------------------------------- #

async def test_opted_in_returns_patient_id() -> None:
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return _consents_response([
            {
                "consentRecord": {
                    "consentType": "PATIENT_DIRECTED_DATA_EXCHANGE",
                    "consentStatus": "OPTED_IN",
                    "patientId": PATIENT_ID,
                },
            },
        ])

    client = _build_client(handler)
    state = await client.get_consent_state(EXTERNAL_ID)

    assert state.patient_id == PATIENT_ID
    assert state.known_by_healthex is True
    # Confirm the query hit the documented endpoint with the right params.
    assert calls[0].url.path == "/v1/patients/consents"
    assert calls[0].url.params["externalId"] == EXTERNAL_ID
    assert calls[0].url.params["projectId"] == PROJECT_ID


# ---------------------------------------------------------------------- #
# Case 2: REVOKED — record type is present but status isn't OPTED_IN.    #
# This is the state Diego's ask depends on: distinguishes revocation    #
# from "never consented". known_by_healthex must be True.               #
# ---------------------------------------------------------------------- #

@pytest.mark.parametrize("revoked_status", ["OPTED_OUT", "REVOKED", "WITHDRAWN"])
async def test_record_exists_but_not_opted_in_is_known_but_no_patient_id(
    revoked_status: str,
) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return _consents_response([
            {
                "consentRecord": {
                    "consentType": "PATIENT_DIRECTED_DATA_EXCHANGE",
                    "consentStatus": revoked_status,
                    "patientId": PATIENT_ID,
                },
            },
        ])

    client = _build_client(handler)
    state = await client.get_consent_state(EXTERNAL_ID)

    assert state.patient_id is None
    assert state.known_by_healthex is True, (
        f"HealthEx returned a {revoked_status} PATIENT_DIRECTED_DATA_EXCHANGE "
        f"record; poll_status uses known_by_healthex=True to fire REVOKED"
    )


# ---------------------------------------------------------------------- #
# Case 3: PENDING — empty results, HealthEx doesn't know this externalId.
# Two shapes: 200 with empty results, and 400 "Patient not found".      #
# ---------------------------------------------------------------------- #

async def test_empty_results_is_pending() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return _consents_response([])

    client = _build_client(handler)
    state = await client.get_consent_state(EXTERNAL_ID)

    assert state.patient_id is None
    assert state.known_by_healthex is False


async def test_400_patient_not_found_is_pending() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, text=json.dumps({"message": "Patient not found for externalId"}),
        )

    client = _build_client(handler)
    state = await client.get_consent_state(EXTERNAL_ID)

    assert state.patient_id is None
    assert state.known_by_healthex is False


async def test_400_with_unfamiliar_short_body_is_pending_with_warning(caplog) -> None:
    """Vendor copy drift shouldn't silently misclassify — logs a WARNING
    so a real behavioural change (e.g. new error type behind the same
    status code) is observable in the tail of the logs."""
    import logging

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text=json.dumps({"error": "unauthorized-project"}))

    client = _build_client(handler)
    with caplog.at_level(logging.WARNING, logger="services.healthex_client"):
        state = await client.get_consent_state(EXTERNAL_ID)

    assert state.patient_id is None
    assert state.known_by_healthex is False
    assert any(
        "unfamiliar body" in r.message for r in caplog.records
    ), "Expected WARNING when 400 body lacks 'patient not found'"


# ---------------------------------------------------------------------- #
# Case 4: unrelated consent types don't count.                          #
# Only PATIENT_DIRECTED_DATA_EXCHANGE should influence the state.       #
# ---------------------------------------------------------------------- #

async def test_other_consent_types_are_ignored() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return _consents_response([
            {
                "consentRecord": {
                    "consentType": "MARKETING",
                    "consentStatus": "OPTED_IN",
                    "patientId": PATIENT_ID,
                },
            },
            {
                "consentRecord": {
                    "consentType": "RESEARCH",
                    "consentStatus": "OPTED_IN",
                    "patientId": PATIENT_ID,
                },
            },
        ])

    client = _build_client(handler)
    state = await client.get_consent_state(EXTERNAL_ID)

    assert state.patient_id is None
    assert state.known_by_healthex is False, (
        "Presence of other consent types must not mark the externalId as "
        "known — poll_status would incorrectly fire REVOKED"
    )


# ---------------------------------------------------------------------- #
# Case 5: real upstream errors bubble as HealthExError.                 #
# ---------------------------------------------------------------------- #

async def test_500_raises_healthex_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream boom")

    client = _build_client(handler)
    with pytest.raises(HealthExError) as excinfo:
        await client.get_consent_state(EXTERNAL_ID)

    assert "500" in str(excinfo.value)


async def test_non_json_body_raises_healthex_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    client = _build_client(handler)
    with pytest.raises(HealthExError):
        await client.get_consent_state(EXTERNAL_ID)
