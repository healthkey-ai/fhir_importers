import base64
import json

import click
import httpx


def jwt_claims(token: str) -> dict:
    _, payload_b64, _ = token.split(".")
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))


def echo_response(r: httpx.Response) -> None:
    """Print status + JSON-or-raw body. Exits non-zero on 4xx/5xx."""
    color = "green" if r.is_success else "red"
    click.secho(f"HTTP {r.status_code}", fg=color)
    try:
        click.echo(json.dumps(r.json(), indent=2, default=str))
    except ValueError:
        click.echo(r.text[:2000])
    if not r.is_success:
        raise SystemExit(1)
