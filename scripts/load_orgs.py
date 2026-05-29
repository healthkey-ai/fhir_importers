"""Convert a JSON array of FHIR Endpoint resources into organizations.json.

The source format is the same shape as the file shipped with healthkey-etl's
healthtree-platform migration: a top-level JSON array of FHIR `Endpoint`
resources, each with at least `name` and `address` fields. This script:

  * slugifies `name` into a stable alias (with `-2`, `-3` suffixes on collision)
  * skips entries missing a name or address
  * de-duplicates by address (keeps first occurrence)
  * prepends the MyChart Central sandbox org for staging

Usage:
  python scripts/load_orgs.py [--input PATH] [--output PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_INPUT = (
    "/home/nick/PycharmProjects/healthkey-etl/legacy/healthtree-platform/"
    "migrations/2024-12-20_fixProviderSecretsForEpic/endpoints.json"
)

MY_CHART_CENTRAL = {
    "alias": "my_chart_central",
    "title": "MyChart Central",
    "endpoint_url": "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
}


def slugify(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-") or "org"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default="organizations.json")
    args = parser.parse_args()

    raw = json.loads(Path(args.input).read_text())
    if not isinstance(raw, list):
        print(f"Expected a JSON array, got {type(raw).__name__}", file=sys.stderr)
        return 1

    skipped_no_name = 0
    skipped_no_address = 0
    skipped_duplicate = 0
    seen_addresses: set[str] = set()
    alias_counts: dict[str, int] = {}
    orgs: list[dict] = [MY_CHART_CENTRAL]

    for entry in raw:
        name = (entry.get("name") or "").strip()
        address = (entry.get("address") or "").strip()
        if not name:
            skipped_no_name += 1
            continue
        if not address:
            skipped_no_address += 1
            continue
        if address in seen_addresses:
            skipped_duplicate += 1
            continue
        seen_addresses.add(address)

        base = slugify(name)
        count = alias_counts.get(base, 0) + 1
        alias_counts[base] = count
        alias = base if count == 1 else f"{base}-{count}"

        orgs.append({"alias": alias, "title": name, "endpoint_url": address})

    Path(args.output).write_text(json.dumps({"organizations": orgs}, indent=2) + "\n")

    print(
        f"Wrote {args.output}: {len(orgs)} organizations "
        f"(1 MyChart Central + {len(orgs) - 1} real)",
        file=sys.stderr,
    )
    print(
        f"Skipped: no_name={skipped_no_name}, no_address={skipped_no_address}, "
        f"duplicate_address={skipped_duplicate}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
