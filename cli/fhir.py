import json
from collections import Counter
from pathlib import Path

import click

from .common import echo_response
from services.service_locator import ServiceLocator


@click.group()
def fhir() -> None:
    """FHIR R4 operations at api.healthex.io/FHIR/R4/."""


@fhir.command()
@click.argument("patient_id")
@click.option("--since", help="ISO timestamp; sent as _since query param.")
@click.option(
    "--out", default="/tmp/healthex_bundle.json",
    help="Write the full bundle here.",
)
@click.option(
    "--print-bundle/--no-print-bundle", default=False,
    help="Echo the full JSON to stdout in addition to saving to --out.",
)
def pull(patient_id, since, out, print_bundle):
    """GET /FHIR/R4/Person/{patient_id}/$everything."""
    s = ServiceLocator.get_healthex_session()
    params = {"_since": since} if since else None
    r = s.get(
        f"/FHIR/R4/Person/{patient_id}/$everything",
        params=params, accept="application/fhir+json",
    )
    if not r.is_success:
        echo_response(r)
        return
    bundle = r.json()
    entries = bundle.get("entry") or []
    types = Counter((e.get("resource") or {}).get("resourceType", "?") for e in entries)
    click.secho(f"HTTP {r.status_code}", fg="green")
    click.echo(
        f"resourceType={bundle.get('resourceType')}, "
        f"type={bundle.get('type')}, entries={len(entries)}"
    )
    for rt, n in types.most_common():
        click.echo(f"  {n:>4} {rt}")
    Path(out).write_text(json.dumps(bundle, indent=2))
    click.echo(f"\nSaved: {out} ({Path(out).stat().st_size} bytes)")
    if print_bundle:
        click.echo(json.dumps(bundle, indent=2))


@fhir.command()
def capability():
    """GET /FHIR/R4/metadata — confirm FHIR server reachable + report summary."""
    s = ServiceLocator.get_healthex_session()
    r = s.get("/FHIR/R4/metadata", accept="application/fhir+json")
    if not r.is_success:
        echo_response(r)
        return
    cs = r.json()
    rest = (cs.get("rest") or [{}])[0]
    resources = sorted({x.get("type") for x in (rest.get("resource") or [])})
    click.secho(f"HTTP {r.status_code}", fg="green")
    click.echo(f"resourceType={cs.get('resourceType')}, fhirVersion={cs.get('fhirVersion')}")
    click.echo(f"software={(cs.get('software') or {}).get('name')}")
    click.echo(f"resources ({len(resources)}): {', '.join(resources[:15])}{'…' if len(resources) > 15 else ''}")
