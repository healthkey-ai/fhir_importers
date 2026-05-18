class FhirParsingError(Exception):
    """Base error raised by the FHIR ingestion service."""


class InvalidBundleError(FhirParsingError):
    """Raised when the input is not a valid FHIR Bundle."""


class UnsupportedFhirVersionError(FhirParsingError):
    """Raised when a Bundle declares a FHIR version with no registered handlers."""


class UnsupportedResourceTypeError(FhirParsingError):
    """Raised when a Bundle entry's resourceType has no registered handler.

    Treated as a soft error per-resource by the orchestrator (skipped, logged).
    """
