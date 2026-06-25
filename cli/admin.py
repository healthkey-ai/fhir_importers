import json

import click

from .common import jwt_claims
from services.service_locator import ServiceLocator


@click.command()
def whoami():
    """Decode the org JWT and show its claims (organizationId, permissions, type)."""
    s = ServiceLocator.get_healthex_session()
    click.echo(json.dumps(jwt_claims(s.org_token()), indent=2, default=str))


@click.command()
@click.confirmation_option(
    prompt="Print the raw bearer token to stdout? Anyone seeing it can call HealthEx as us.",
)
def token():
    """Print the raw org JWT to stdout (e.g. for curl piping)."""
    s = ServiceLocator.get_healthex_session()
    click.echo(s.org_token())
