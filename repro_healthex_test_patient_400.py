#!/usr/bin/env python3
"""Reproduce: POST /v1/organizations/{orgId}/test-patients returns 400.

Run from the repo root:
    venv/bin/python repro_healthex_test_patient_400.py

Requires HEALTHEX_API_KEY / HEALTHEX_API_SECRET in .env.
"""
import base64
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

BASE = os.environ.get("HEALTHEX_BASE_URL", "https://api.healthex.io")

token = httpx.post(
    f"{BASE}/v1/auth/token",
    json={
        "apiKey": os.environ["HEALTHEX_API_KEY"],
        "apiSecret": os.environ["HEALTHEX_API_SECRET"],
    },
).raise_for_status().json()["token"]

org_id = json.loads(
    base64.urlsafe_b64decode(token.split(".")[1] + "===")
)["organizationId"]

r = httpx.post(
    f"{BASE}/v1/organizations/{org_id}/test-patients",
    headers={"Authorization": f"Bearer {token}"},
    json={"firstName": "Test", "lastName": "Patient", "dateOfBirth": "1990-01-15"},
)
print(f"POST /v1/organizations/{org_id}/test-patients")
print(f"HTTP {r.status_code}")
print(r.text)
