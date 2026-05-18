"""FHIR date/time helpers shared across resource handlers.

FHIR `dateTime` can be:
- YYYY                       → year only
- YYYY-MM                    → year + month
- YYYY-MM-DD                 → date
- YYYY-MM-DDThh:mm:ss[.sss][Z|±hh:mm]   → datetime
"""
from __future__ import annotations

import logging
from datetime import date, datetime

_logger = logging.getLogger(__name__)


def parse_datetime(value: str | None) -> datetime | None:
    """Best-effort parse of a FHIR dateTime/instant string.

    Accepts the full datetime forms and date-only (promoting to midnight UTC).
    Returns None for unparseable input. Logs at debug — bad dates are common.
    """
    if not value:
        return None
    try:
        # Python 3.11+ handles trailing Z natively.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    _logger.debug("Unparseable FHIR datetime: %r", value)
    return None


def parse_date(value: str | None) -> date | None:
    """Best-effort parse of a FHIR `date`. Falls back to truncating a datetime."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        dt = parse_datetime(value)
        return dt.date() if dt is not None else None
