#!/usr/bin/env python3
"""Diagnose: HealthEx UI says 'Active' but API says 'Patient not found'.

Tries the consent-lookup against both consent types + lists consented patients
in the project. One of these should reveal where the patient actually landed.
"""
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

if len(sys.argv) != 2:
    sys.exit("Usage: debug_consent.py <external_id>")
EXTERNAL_ID = sys.argv[1]

BASE = os.environ.get("HEALTHEX_BASE_URL", "https://api.healthex.io")
PROJ = os.environ["HEALTHEX_PROJECT_ID"]

token = httpx.post(
    f"{BASE}/v1/auth/token",
    json={
        "apiKey": os.environ["HEALTHEX_API_KEY"],
        "apiSecret": os.environ["HEALTHEX_API_SECRET"],
    },
).raise_for_status().json()["token"]
H = {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def probe(method, path, **kw):
    url = f"{BASE}{path}"
    r = httpx.request(method, url, headers=H, **kw)
    body = r.text[:500].replace("\n", " ")
    print(f"  {r.status_code}  {method} {path[:90]:90s} {body}")


print(f"externalId = {EXTERNAL_ID!r}, projectId = {PROJ}")
print()

print("--- Try both consent types in the parametric endpoint ---")
for ctype in ("PATIENT_DIRECTED_DATA_EXCHANGE", "DATA_AUTHORIZATION"):
    probe("GET",
          f"/v1/patients/consented/study/{PROJ}/{ctype}",
          params={"externalId": EXTERNAL_ID})

print()
print("--- List-style endpoints (no consent-type filter or list all) ---")
for path in [
    f"/v1/patients/consented/study/{PROJ}",
    f"/v1/projects/{PROJ}/consented-patients",
    f"/v1/projects/{PROJ}/patients",
]:
    probe("GET", path)
