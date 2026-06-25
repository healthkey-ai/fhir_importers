#!/usr/bin/env python3
"""Verify a consented patient: externalId → patientId → $everything.

Run after completing consent in the browser:
    venv/bin/python verify_consent.py <external_id>
"""
import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.healthex_client import HealthExClient

if len(sys.argv) != 2:
    sys.exit("Usage: verify_consent.py <external_id>")
EXTERNAL_ID = sys.argv[1]
BASE = os.environ.get("HEALTHEX_BASE_URL", "https://api.healthex.io")
PROJECT = os.environ["HEALTHEX_PROJECT_ID"]


async def main() -> None:
    async with httpx.AsyncClient(timeout=60.0) as http:
        client = HealthExClient(
            http=http, base_url=BASE,
            api_key=os.environ["HEALTHEX_API_KEY"],
            api_secret=os.environ["HEALTHEX_API_SECRET"],
        )

        print(f"--- find_patient_id_by_external_id({EXTERNAL_ID!r}) ---")
        pid = await client.find_patient_id_by_external_id(
            project_id=PROJECT, external_id=EXTERNAL_ID,
        )
        if pid is None:
            print("Still pending (HTTP 400 'Patient not found'). Wait a few seconds and re-run.")
            return
        print(f"patient_id: {pid}")

        # Capture the raw 200 response — first time we'll see this shape.
        print("\n--- raw response of the consented-patients endpoint ---")
        token = await client._access_token()
        raw = await http.get(
            f"{BASE}/v1/patients/consented/study/{PROJECT}/PATIENT_DIRECTED_DATA_EXCHANGE",
            params={"externalId": EXTERNAL_ID},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        print(f"HTTP {raw.status_code}")
        try:
            print(json.dumps(raw.json(), indent=2, default=str)[:2000])
        except Exception:
            print(raw.text[:500])

        print(f"\n--- GET /FHIR/R4/Person/{pid}/$everything ---")
        r = await http.get(
            f"{BASE}/FHIR/R4/Person/{pid}/$everything",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/fhir+json",
            },
            timeout=120.0,
        )
        print(f"HTTP {r.status_code}")
        if r.status_code >= 400:
            print(r.text[:600])
            return
        bundle = r.json()
        entries = bundle.get("entry", []) or []
        types = Counter(
            (e.get("resource") or {}).get("resourceType", "?") for e in entries
        )
        print(f"resourceType={bundle.get('resourceType')}, type={bundle.get('type')}, entries={len(entries)}")
        for rt, n in types.most_common():
            print(f"  {n:>4} {rt}")
        out = Path("/tmp/healthex_bundle.json")
        out.write_text(json.dumps(bundle, indent=2))
        print(f"\nFull bundle saved: {out} ({out.stat().st_size} bytes)")


asyncio.run(main())
