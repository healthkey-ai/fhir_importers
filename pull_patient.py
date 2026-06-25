#!/usr/bin/env python3
"""GET /FHIR/R4/Person/{patient_id}/$everything → print summary, save bundle.

Run:
    venv/bin/python pull_patient.py <patient_id>
    venv/bin/python pull_patient.py <patient_id> --since 2026-06-24T00:00:00Z
"""
import argparse
import json
import os
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

parser = argparse.ArgumentParser()
parser.add_argument("patient_id")
parser.add_argument("--since", help="ISO timestamp for incremental delta")
parser.add_argument("--out", default="/tmp/healthex_bundle.json")
args = parser.parse_args()

BASE = os.environ.get("HEALTHEX_BASE_URL", "https://api.healthex.io")

token = httpx.post(
    f"{BASE}/v1/auth/token",
    json={
        "apiKey": os.environ["HEALTHEX_API_KEY"],
        "apiSecret": os.environ["HEALTHEX_API_SECRET"],
    },
).raise_for_status().json()["token"]

params = {"_since": args.since} if args.since else None
r = httpx.get(
    f"{BASE}/FHIR/R4/Person/{args.patient_id}/$everything",
    params=params,
    headers={"Authorization": f"Bearer {token}", "Accept": "application/fhir+json"},
    timeout=120.0,
)
print(f"HTTP {r.status_code}")
if r.status_code >= 400:
    print(r.text[:600])
    raise SystemExit(1)

bundle = r.json()
entries = bundle.get("entry", []) or []
types = Counter((e.get("resource") or {}).get("resourceType", "?") for e in entries)
print(f"resourceType={bundle.get('resourceType')}, type={bundle.get('type')}, entries={len(entries)}")
for rt, n in types.most_common():
    print(f"  {n:>4} {rt}")

out = Path(args.out)
out.write_text(json.dumps(bundle, indent=2))
print(f"\nSaved: {out} ({out.stat().st_size} bytes)")
