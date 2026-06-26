import click

from services.healthex_client import HealthExError
from services.service_locator import ServiceLocator

from .common import async_command, echo_http_error, echo_response_dict


@click.group(name="test-patient")
def test_patient() -> None:
    """Synthetic test-patient management (CI / no-browser test affordance)."""


@test_patient.command()
@click.option("--first-name", default="Test")
@click.option("--last-name", default="Patient")
@click.option("--dob", default="1990-01-15", help="YYYY-MM-DD")
@async_command
async def create(first_name, last_name, dob):
    """Create a test patient (HealthEx auto-generates email + password)."""
    async with ServiceLocator.healthex_client() as client:
        try:
            data = await client.create_test_patient(
                first_name=first_name, last_name=last_name, date_of_birth=dob,
            )
        except HealthExError as exc:
            echo_http_error(exc)
        click.secho(
            "Test patient created. SAVE THE PASSWORD NOW — shown only once.",
            fg="yellow", bold=True,
        )
        echo_response_dict(data)


@test_patient.command("list")
@async_command
async def list_():
    """List all test patients in our org."""
    async with ServiceLocator.healthex_client() as client:
        try:
            patients = await client.list_test_patients()
        except HealthExError as exc:
            echo_http_error(exc)
        echo_response_dict(patients)


@test_patient.command()
@click.argument("patient_id")
@async_command
async def delete(patient_id):
    """Delete a test patient by id."""
    async with ServiceLocator.healthex_client() as client:
        try:
            await client.delete_test_patient(patient_id)
        except HealthExError as exc:
            echo_http_error(exc)
        click.secho(f"deleted {patient_id}", fg="green")
