import click

from .common import echo_response
from services.service_locator import ServiceLocator


@click.group()
def patient() -> None:
    """addPatients, Unique Link, externalId → patientId lookup."""


def _add_patient_body(
    *, external_id: str, email: str, first_name: str, last_name: str,
    language: str, contact_pref: str, suppress: bool,
) -> dict:
    return {
        "patients": [{
            "externalId": external_id,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "languagePreference": language,
            "contactPreference": contact_pref,
        }],
        "suppressNotifications": suppress,
    }


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
def add(external_id, email, first_name, last_name, language, contact_pref, notify):
    """Register a Recruitment (addPatients) for an externalId."""
    s = ServiceLocator.get_healthex_session()
    r = s.post(
        f"/v1/projects/{s.project_id}/patients",
        json=_add_patient_body(
            external_id=external_id, email=email,
            first_name=first_name, last_name=last_name,
            language=language, contact_pref=contact_pref,
            suppress=not notify,
        ),
    )
    echo_response(r)


@patient.command()
@click.argument("external_id", required=False)
def link(external_id):
    """Mint a Unique Link for an externalId (omit for the generic project link)."""
    s = ServiceLocator.get_healthex_session()
    body = {"externalId": external_id} if external_id else {}
    r = s.post(f"/v1/projects/{s.project_id}/link", json=body)
    if not r.is_success:
        echo_response(r)
        return
    click.echo(r.text.strip())


@patient.command()
@click.argument("external_id")
def find(external_id):
    """Resolve externalId → patientId via getPatientConsents (OPTED_IN PDDE only)."""
    s = ServiceLocator.get_healthex_session()
    r = s.get(
        "/v1/patients/consents",
        params={"externalId": external_id, "projectId": s.project_id},
    )
    if not r.is_success:
        echo_response(r)
        return
    for entry in r.json().get("results", []) or []:
        cr = (entry or {}).get("consentRecord") or {}
        if (cr.get("consentType") == "PATIENT_DIRECTED_DATA_EXCHANGE"
                and cr.get("consentStatus") == "OPTED_IN"
                and cr.get("patientId")):
            click.echo(cr["patientId"])
            return
    click.secho(
        "(no OPTED_IN PATIENT_DIRECTED_DATA_EXCHANGE consent found — still pending or revoked)",
        fg="yellow",
    )
    raise SystemExit(2)


@patient.command()
@click.argument("patient_id")
def demographics(patient_id):
    """GET /v1/projects/{p}/patients/{patient_id}/demographics."""
    s = ServiceLocator.get_healthex_session()
    r = s.get(f"/v1/projects/{s.project_id}/patients/{patient_id}/demographics")
    echo_response(r)


@click.command()
@click.argument("external_id")
@click.option("--email", required=True)
@click.option("--first-name", default="Test")
@click.option("--last-name", default="User")
def connect(external_id, email, first_name, last_name):
    """addPatients + mint Unique Link (mirrors /healthex/connect production flow)."""
    s = ServiceLocator.get_healthex_session()
    r1 = s.post(
        f"/v1/projects/{s.project_id}/patients",
        json=_add_patient_body(
            external_id=external_id, email=email,
            first_name=first_name, last_name=last_name,
            language="en", contact_pref="email", suppress=True,
        ),
    )
    if not r1.is_success:
        click.secho("addPatients failed:", fg="red")
        echo_response(r1)
        return
    click.secho(f"addPatients → HTTP {r1.status_code}", fg="green")

    r2 = s.post(f"/v1/projects/{s.project_id}/link", json={"externalId": external_id})
    if not r2.is_success:
        click.secho("link mint failed:", fg="red")
        echo_response(r2)
        return
    click.secho(f"link → HTTP {r2.status_code}", fg="green")
    click.echo(f"\n{r2.text.strip()}")
