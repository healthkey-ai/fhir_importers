import json
from collections import Counter
from pathlib import Path

import click

from services.healthex_client import HealthExError
from services.service_locator import ServiceLocator

from .common import async_command, echo_http_error


@click.group()
def fhir() -> None:
    """FHIR R4 operations on api.healthex.io/FHIR/R4/."""


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
@async_command
async def pull(patient_id, since, out, print_bundle):
    """GET /FHIR/R4/Person/{patient_id}/$everything → summary + save."""
    async with ServiceLocator.healthex_client() as client:
        try:
            bundle = await client.pull_everything(patient_id, since=since)
        except HealthExError as exc:
            echo_http_error(exc)

    entries = bundle.get("entry") or []
    types = Counter((e.get("resource") or {}).get("resourceType", "?") for e in entries)
    click.secho("ok", fg="green")
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
@async_command
async def capability():
    """GET /FHIR/R4/metadata — confirm FHIR server reachable + summary."""
    async with ServiceLocator.healthex_client() as client:
        try:
            cs = await client.get_capability_statement()
        except HealthExError as exc:
            echo_http_error(exc)
    rest = (cs.get("rest") or [{}])[0]
    resources = sorted({x.get("type") for x in (rest.get("resource") or [])})
    click.secho("ok", fg="green")
    click.echo(f"resourceType={cs.get('resourceType')}, fhirVersion={cs.get('fhirVersion')}")
    click.echo(f"software={(cs.get('software') or {}).get('name')}")
    click.echo(
        f"resources ({len(resources)}): "
        f"{', '.join(resources[:15])}{'…' if len(resources) > 15 else ''}"
    )
