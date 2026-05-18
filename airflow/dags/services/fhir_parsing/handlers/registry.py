import logging

from services.fhir_parsing.fhir_parsing_errors import (
    UnsupportedFhirVersionError,
    UnsupportedResourceTypeError,
)
from services.fhir_parsing.fhir_parsing_types import FhirResourceType, FhirVersion
from services.fhir_parsing.handlers.abstract_resource_handler import AbstractResourceHandler

_logger = logging.getLogger(__name__)

HandlerKey = tuple[FhirVersion, FhirResourceType]


class ResourceHandlerRegistry:
    """Looks up a resource handler by (FhirVersion, FhirResourceType)."""

    def __init__(self, handlers: dict[HandlerKey, AbstractResourceHandler]):
        self._handlers = handlers

    def get(self, version: FhirVersion, resource_type: FhirResourceType) -> AbstractResourceHandler:
        try:
            return self._handlers[(version, resource_type)]
        except KeyError as e:
            if not any(v == version for v, _ in self._handlers):
                raise UnsupportedFhirVersionError(str(version)) from e
            raise UnsupportedResourceTypeError(
                f"{resource_type} for FHIR {version}"
            ) from e

    def has(self, version: FhirVersion, resource_type: FhirResourceType) -> bool:
        return (version, resource_type) in self._handlers


def build_default_registry() -> ResourceHandlerRegistry:
    """Constructs the registry pre-wired with the r4 handlers.

    Kept here (rather than passed in) so DAG/service composition stays simple:
    the registry is stateless and handlers have no external dependencies.
    """
    from services.fhir_parsing.handlers.r4.patient_handler import PatientResourceHandler
    from services.fhir_parsing.handlers.r4.condition_handler import ConditionResourceHandler
    from services.fhir_parsing.handlers.r4.observation_handler import ObservationResourceHandler
    from services.fhir_parsing.handlers.r4.medication_statement_handler import (
        MedicationStatementResourceHandler,
    )
    from services.fhir_parsing.handlers.r4.procedure_handler import ProcedureResourceHandler

    handlers: dict[HandlerKey, AbstractResourceHandler] = {
        (FhirVersion.R4, FhirResourceType.PATIENT): PatientResourceHandler(),
        (FhirVersion.R4, FhirResourceType.CONDITION): ConditionResourceHandler(),
        (FhirVersion.R4, FhirResourceType.OBSERVATION): ObservationResourceHandler(),
        (FhirVersion.R4, FhirResourceType.MEDICATION_STATEMENT): MedicationStatementResourceHandler(),
        (FhirVersion.R4, FhirResourceType.PROCEDURE): ProcedureResourceHandler(),
    }
    return ResourceHandlerRegistry(handlers)
