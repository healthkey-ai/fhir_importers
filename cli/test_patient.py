import json

import click

from .common import echo_response
from services.service_locator import ServiceLocator


@click.group(name="test-patient")
def test_patient() -> None:
    """Synthetic test-patient management (CI / no-browser test affordance)."""


@test_patient.command()
@click.option("--first-name", default="Test")
@click.option("--last-name", default="Patient")
@click.option("--dob", default="1990-01-15", help="YYYY-MM-DD")
def create(first_name, last_name, dob):
    """Create a test patient (HealthEx auto-generates email + password)."""
    s = ServiceLocator.get_healthex_session()
    r = s.post(
        f"/v1/organizations/{s.org_id()}/test-patients",
        json={"firstName": first_name, "lastName": last_name, "dateOfBirth": dob},
    )
    if not r.is_success:
        echo_response(r)
        return
    click.secho(
        "Test patient created. SAVE THE PASSWORD NOW — shown only once.",
        fg="yellow", bold=True,
    )
    click.echo(json.dumps(r.json(), indent=2))


@test_patient.command("list")
def list_():
    """List all test patients in our org."""
    s = ServiceLocator.get_healthex_session()
    r = s.get(f"/v1/organizations/{s.org_id()}/test-patients")
    echo_response(r)


@test_patient.command()
@click.argument("patient_id")
def delete(patient_id):
    """Delete a test patient by id."""
    s = ServiceLocator.get_healthex_session()
    r = s.delete(f"/v1/organizations/{s.org_id()}/test-patients/{patient_id}")
    color = "green" if r.is_success else "red"
    click.secho(f"HTTP {r.status_code}", fg=color)
    if r.text:
        click.echo(r.text[:500])
