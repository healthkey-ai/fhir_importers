#!/usr/bin/env python3
"""Drive the test-patient auth + consent flow without a browser.

Steps (per docs.healthex.io/test-patients/):
  1. Mint patient JWT via /v1/auth/token with email + password
  2. Add patient to project via org JWT (suppressNotifications=true)
  3. Opt-in consent via patient JWT
  4. Fetch $everything via org JWT to verify

Requires in .env:
    HEALTHEX_API_KEY / HEALTHEX_API_SECRET / HEALTHEX_PROJECT_ID
    HEALTHEX_TEST_PATIENT_EMAIL / HEALTHEX_TEST_PATIENT_PASSWORD / HEALTHEX_TEST_PATIENT_ID

Run from the repo root:
    venv/bin/python test_healthex_patient_auth.py
"""
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

BASE = os.environ.get("HEALTHEX_BASE_URL", "https://api.healthex.io")
PROJECT_ID = os.environ["HEALTHEX_PROJECT_ID"]
PATIENT_EMAIL = os.environ["HEALTHEX_TEST_PATIENT_EMAIL"]
PATIENT_PASSWORD = os.environ["HEALTHEX_TEST_PATIENT_PASSWORD"]
PATIENT_ID = os.environ["HEALTHEX_TEST_PATIENT_ID"]


def step(n: int, label: str) -> None:
    print(f"\n--- {n}. {label} ---")


step(1, "Mint patient JWT (POST /v1/auth/token with email+password)")
patient_token = httpx.post(
    f"{BASE}/v1/auth/token",
    json={"email": PATIENT_EMAIL, "password": PATIENT_PASSWORD},
).raise_for_status().json()["token"]
print(f"patient token: {patient_token[:24]}…(len={len(patient_token)})")

step(2, "Mint org JWT (POST /v1/auth/token with apiKey+apiSecret)")
org_token = httpx.post(
    f"{BASE}/v1/auth/token",
    json={
        "apiKey": os.environ["HEALTHEX_API_KEY"],
        "apiSecret": os.environ["HEALTHEX_API_SECRET"],
    },
).raise_for_status().json()["token"]
print(f"org token:     {org_token[:24]}…(len={len(org_token)})")

step(3, f"Add test patient to project {PROJECT_ID} (org JWT)")
r = httpx.post(
    f"{BASE}/v1/projects/{PROJECT_ID}/patients",
    headers={"Authorization": f"Bearer {org_token}"},
    json={
        "patients": [{
            "email": PATIENT_EMAIL,
            "firstName": "Test",
            "lastName": "Patient",
            "languagePreference": "en",
        }],
        "suppressNotifications": True,
    },
)
print(f"HTTP {r.status_code}: {r.text}")

step(4, f"Opt-in consent (patient JWT)")
r = httpx.post(
    f"{BASE}/v1/projects/{PROJECT_ID}/test-patients/{PATIENT_ID}/consent",
    headers={"Authorization": f"Bearer {patient_token}"},
    json={"consentStatus": "OPTED_IN"},
)
print(f"HTTP {r.status_code}: {r.text}")

step(5, f"GET /FHIR/R4/Person/{PATIENT_ID}/$everything (org JWT)")
r = httpx.get(
    f"{BASE}/FHIR/R4/Person/{PATIENT_ID}/$everything",
    headers={
        "Authorization": f"Bearer {org_token}",
        "Accept": "application/fhir+json",
    },
    timeout=60.0,
)
print(f"HTTP {r.status_code}")
if r.status_code < 400:
    bundle = r.json()
    entries = bundle.get("entry", []) or []
    from collections import Counter
    types = Counter((e.get("resource") or {}).get("resourceType", "?") for e in entries)
    print(f"  resourceType={bundle.get('resourceType')}, entries={len(entries)}")
    for rt, n in types.most_common():
        print(f"    {n:>4}  {rt}")
else:
    print(f"  body: {r.text[:400]}")
