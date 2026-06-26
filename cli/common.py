import asyncio
import functools
import json

import click
import httpx


def async_command(coro):
    """Wrap an async function so click can invoke it as a sync command.

    Lets command bodies use `await` directly while keeping click's signature
    expectations (decorators expect a regular callable).
    """
    @functools.wraps(coro)
    def wrapper(*args, **kwargs):
        return asyncio.run(coro(*args, **kwargs))
    return wrapper


def echo_response_dict(data: dict | list) -> None:
    """Pretty-print a JSON-shaped value to stdout."""
    click.echo(json.dumps(data, indent=2, default=str))


def echo_http_error(exc: Exception) -> None:
    """Print an upstream-failure message in red and exit non-zero."""
    click.secho(f"error: {exc}", fg="red")
    raise SystemExit(1)
