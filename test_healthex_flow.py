#!/usr/bin/env python3
"""Manual end-to-end test of the HealthEx consumer-pull flow.

Run from the repo root with:
    venv/bin/python test_healthex_flow.py

Requires HEALTHEX_API_KEY / HEALTHEX_API_SECRET / HEALTHEX_PROJECT_ID in .env.

Flow:
  1. Mint a Unique Link for EXTERNAL_ID.
  2. You open the link in a browser, finish CLEAR + consent.
     HealthEx does NOT redirect back — no callback URL to paste.
  3. Hit `c` in pdb; the script polls for patientId, then for data-retrieval
     status, then GETs $everything and dumps a summary.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import httpx  # noqa: E402

from app.healthex_client import HealthExClient, HealthExError  # noqa: E402


EXTERNAL_ID = "nick-e2e-smoke-001"
BUNDLE_OUTPUT = Path("/tmp/healthex_bundle.json")


async def main() -> None:
    base = os.environ.get("HEALTHEX_BASE_URL", "https://api.healthex.io")
    project_id = os.environ["HEALTHEX_PROJECT_ID"]

    async with httpx.AsyncClient(timeout=30.0) as http:
        client = HealthExClient(
            http=http,
            base_url=base,
            api_key=os.environ["HEALTHEX_API_KEY"],
            api_secret=os.environ["HEALTHEX_API_SECRET"],
        )

        # ---------------------------------------------------------------- #
        # Step 1 — mint Unique Link
        # ---------------------------------------------------------------- #
        print(f"\n=== Step 1: get_unique_link(external_id={EXTERNAL_ID!r}) ===")
        onboarding_url = await client.get_unique_link(
            project_id=project_id, external_id=EXTERNAL_ID,
        )
        print(f"\n  {onboarding_url}\n")

        print("=" * 78)
        print("OPEN THE URL ABOVE IN A BROWSER")
        print("  1. Sign up or log in to HealthEx")
        print("  2. Complete CLEAR identity verification (real ID needed)")
        print("  3. Grant consent to share your data")
        print()
        print("There is NO callback to us. HealthEx will not redirect anywhere")
        print("useful when you finish — just close the tab and resume here.")
        print()
        print("At the (Pdb) prompt:")
        print("  - Hit 'c' to continue (default behavior).")
        print("  - Or override the external_id used for polling:")
        print("        (Pdb) external_id_override = 'some-other-id'")
        print("        (Pdb) c")
        print("=" * 78)

        external_id_override: str | None = None
        breakpoint()  # noqa: T100

        target_external_id = external_id_override or EXTERNAL_ID

        # ---------------------------------------------------------------- #
        # Step 2 — poll for patientId until consent completes
        # ---------------------------------------------------------------- #
        print(
            f"\n=== Step 2: poll find_patient_id_by_external_id"
            f"({target_external_id!r}) ==="
        )
        patient_id: str | None = None
        for attempt in range(1, 25):  # ~2 minutes at 5s
            try:
                patient_id = await client.find_patient_id_by_external_id(
                    project_id=project_id, external_id=target_external_id,
                )
            except HealthExError as exc:
                print(f"  attempt {attempt:>2}: ERROR {exc}")
                return
            if patient_id:
                print(f"  attempt {attempt:>2}: patientId={patient_id}")
                break
            print(f"  attempt {attempt:>2}: still pending — sleeping 5s")
            await asyncio.sleep(5)
        else:
            print("\n  Timed out. Re-run after you've finished consent in browser.")
            return

        # ---------------------------------------------------------------- #
        # Step 3 — poll data-retrieval status until COMPLETE (best-effort)
        # ---------------------------------------------------------------- #
        print(f"\n=== Step 3: poll data-retrieval status for patient {patient_id} ===")
        for attempt in range(1, 31):  # ~5 minutes at 10s
            try:
                status = await client.get_data_retrieval_status(
                    project_id=project_id, patient_id=patient_id,
                )
            except HealthExError as exc:
                # 403 etc. is a known unknown — skip this phase and try fetch anyway.
                print(f"  attempt {attempt:>2}: status call failed ({exc}); skipping")
                break
            print(
                f"  attempt {attempt:>2}: overall={status.overall_status!r}, "
                f"vectorization={status.vectorization_status!r}"
            )
            if status.overall_status.upper() in {"COMPLETE", "COMPLETED"}:
                break
            await asyncio.sleep(10)

        # ---------------------------------------------------------------- #
        # Step 4 — GET $everything and summarize
        # ---------------------------------------------------------------- #
        print(f"\n=== Step 4: GET /FHIR/R4/Person/{patient_id}/$everything ===")
        token = await client._access_token()
        response = await http.get(
            f"{base}/FHIR/R4/Person/{patient_id}/$everything",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/fhir+json",
            },
            timeout=180.0,
        )
        print(f"  HTTP {response.status_code}")
        if response.status_code >= 400:
            print(f"  body: {response.text[:1000]}")
            return

        bundle = response.json()
        entries = bundle.get("entry", []) or []
        print(f"  resourceType={bundle.get('resourceType')}, type={bundle.get('type')}")
        print(f"  entries={len(entries)}")

        types = Counter(
            (e.get("resource") or {}).get("resourceType", "?") for e in entries
        )
        print("  resources by type:")
        for rt, n in types.most_common():
            print(f"    {n:>5}  {rt}")

        BUNDLE_OUTPUT.write_text(json.dumps(bundle, indent=2))
        print(
            f"\n  Saved full bundle: {BUNDLE_OUTPUT} "
            f"({BUNDLE_OUTPUT.stat().st_size:,} bytes)"
        )


if __name__ == "__main__":
    asyncio.run(main())
