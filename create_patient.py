#!/usr/bin/env python3
"""Add a patient via addPatients, then mint a Unique Link for the same externalId.

Tests the hypothesis that the Unique Link consent flow requires a Recruitment
record (created by addPatients) — the previous attempt without addPatients hit
'Recruitment not found'.

Run:
    venv/bin/python create_patient.py <your-email>
"""
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

if len(sys.argv) != 2:
    sys.exit("Usage: create_patient.py <email>")
EMAIL = sys.argv[1]

BASE = os.environ.get("HEALTHEX_BASE_URL", "https://api.healthex.io")
PROJ = os.environ["HEALTHEX_PROJECT_ID"]

# Fresh externalId per run so we don't reuse the broken state from the prior
# Unique Link mint. Bake the email's local-part in for traceability.
EXTERNAL_ID = f"nick-add-{EMAIL.split('@')[0]}-001"
print(f"Using externalId: {EXTERNAL_ID}")

token = httpx.post(
    f"{BASE}/v1/auth/token",
    json={
        "apiKey": os.environ["HEALTHEX_API_KEY"],
        "apiSecret": os.environ["HEALTHEX_API_SECRET"],
    },
).raise_for_status().json()["token"]
H = {"Authorization": f"Bearer {token}"}

print(f"\n--- POST /v1/projects/{PROJ}/patients (addPatients, suppressNotifications=true) ---")
r = httpx.post(
    f"{BASE}/v1/projects/{PROJ}/patients",
    headers=H,
    json={
        "patients": [{
            "externalId": EXTERNAL_ID,
            "email": EMAIL,
            "firstName": "Nikita",
            "lastName": "Shpilevoy",
            "languagePreference": "en",
            "contactPreference": "email",
        }],
        "suppressNotifications": True,
    },
)
print(f"HTTP {r.status_code}")
print(r.text)
if r.status_code >= 400:
    sys.exit("addPatients failed; stopping.")

print(f"\n--- POST /v1/projects/{PROJ}/link ---")
r = httpx.post(
    f"{BASE}/v1/projects/{PROJ}/link",
    headers=H,
    json={"externalId": EXTERNAL_ID},
).raise_for_status()
link = r.text.strip()
print(f"\nOpen this link in a browser, sign in with Google, complete consent:")
print(f"\n  {link}\n")
print("If 'Recruitment not found' DOES NOT appear at the Confirm step → addPatients is required (docs are wrong).")
print("If it still 404s → it's a Google-sign-in / identity-tier issue, ticket to Diana.")
