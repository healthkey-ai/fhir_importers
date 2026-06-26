import click

from services.healthex_client import HealthExError
from services.service_locator import ServiceLocator

from .common import async_command, echo_http_error, echo_response_dict


@click.group()
def patient() -> None:
    """addPatients, Unique Link, externalId → patientId lookup."""


@patient.command()
@click.argument("external_id")
@click.option("--email", required=True)
@click.option("--first-name", default="Test")
@click.option("--last-name", default="User")
@click.option("--language", default="en")
@click.option("--contact-pref", type=click.Choice(["email", "phone"]), default="email")
@click.option(
    "--notify/--no-notify", default=False,
    help="Fire HealthEx-managed outreach (default: suppress).",
)
@async_command
async def add(external_id, email, first_name, last_name, language, contact_pref, notify):
    """Register a Recruitment (addPatients) for an externalId."""
    async with ServiceLocator.healthex_client() as client:
        try:
            result = await client.add_patient(
                external_id=external_id,
                email=email,
                first_name=first_name,
                last_name=last_name,
                language=language,
                contact_pref=contact_pref,
                suppress_notifications=not notify,
            )
        except HealthExError as exc:
            echo_http_error(exc)
        echo_response_dict(result)


@patient.command()
@click.argument("external_id", required=False)
@async_command
async def link(external_id):
    """Mint a Unique Link for an externalId (omit for the generic project link)."""
    async with ServiceLocator.healthex_client() as client:
        try:
            click.echo(await client.get_unique_link(external_id))
        except HealthExError as exc:
            echo_http_error(exc)


@patient.command()
@click.argument("external_id")
@async_command
async def find(external_id):
    """Resolve externalId → patientId (OPTED_IN PATIENT_DIRECTED_DATA_EXCHANGE)."""
    async with ServiceLocator.healthex_client() as client:
        try:
            patient_id = await client.find_patient_id_by_external_id(external_id)
        except HealthExError as exc:
            echo_http_error(exc)
        if patient_id:
            click.echo(patient_id)
            return
        click.secho(
            "(no OPTED_IN PATIENT_DIRECTED_DATA_EXCHANGE consent found — "
            "still pending or revoked)",
            fg="yellow",
        )
        raise SystemExit(2)


@patient.command()
@click.argument("patient_id")
@async_command
async def demographics(patient_id):
    """Fetch a patient's demographics by patient_id."""
    async with ServiceLocator.healthex_client() as client:
        try:
            data = await client.get_demographics(patient_id)
        except HealthExError as exc:
            echo_http_error(exc)
        echo_response_dict(data)


@click.command()
@click.argument("external_id")
@click.option("--email", required=True)
@click.option("--first-name", default="Test")
@click.option("--last-name", default="User")
@async_command
async def connect(external_id, email, first_name, last_name):
    """addPatients + mint Unique Link (mirrors /healthex/connect production flow)."""
    async with ServiceLocator.healthex_client() as client:
        try:
            await client.add_patient(
                external_id=external_id, email=email,
                first_name=first_name, last_name=last_name,
                suppress_notifications=True,
            )
            link_url = await client.get_unique_link(external_id)
        except HealthExError as exc:
            echo_http_error(exc)
        click.secho("connect ok", fg="green")
        click.echo(link_url)
