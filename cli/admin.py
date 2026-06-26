import click

from services.healthex_client import HealthExError
from services.service_locator import ServiceLocator

from .common import async_command, echo_http_error, echo_response_dict


@click.command()
@async_command
async def whoami():
    """Decode the org JWT and show its claims."""
    async with ServiceLocator.healthex_client() as client:
        try:
            echo_response_dict(await client.jwt_claims())
        except HealthExError as exc:
            echo_http_error(exc)


@click.command()
@click.confirmation_option(
    prompt="Print the raw bearer token to stdout? Anyone seeing it can call HealthEx as us.",
)
@async_command
async def token():
    """Print the raw org JWT to stdout (e.g. for curl piping)."""
    async with ServiceLocator.healthex_client() as client:
        try:
            click.echo(await client.org_jwt())
        except HealthExError as exc:
            echo_http_error(exc)
