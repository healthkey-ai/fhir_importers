import abc
from typing import Any

from services.fhir_parsing.fhir_parsing_types import ParsedPatientPayload


class AbstractResourceHandler(abc.ABC):
    """Parses a single FHIR resource and merges the result into the patient payload.

    One concrete handler per (FhirVersion, FhirResourceType). The registry
    dispatches on that pair so a Bundle declared as STU3 routes Observations
    to `handlers/stu3/observation_handler.py`, not the r4 implementation.
    """

    @abc.abstractmethod
    def handle(self, resource: dict[str, Any], payload: ParsedPatientPayload) -> None:
        raise NotImplementedError
