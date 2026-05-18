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
    """Constructs the registry with every supported version + resourceType combo.

    - r4 has full coverage (Patient/Condition/Observation/MedicationStatement/MedicationRequest/Procedure).
    - stu3 reuses r4 Patient + r4 Procedure unchanged; Observation, Condition,
      and MedicationRequest are stu3-specific wrappers that handle the
      pre-r4 field renames.
    - dstu2 reuses r4 Patient unchanged; Procedure, Observation, Condition
      each have a small wrapper. MedicationOrder is the dstu2 name for what
      became MedicationRequest in stu3+.
    """
    from services.fhir_parsing.handlers.r4.patient_handler import PatientResourceHandler
    from services.fhir_parsing.handlers.r4.condition_handler import ConditionResourceHandler
    from services.fhir_parsing.handlers.r4.observation_handler import ObservationResourceHandler
    from services.fhir_parsing.handlers.r4.medication_statement_handler import (
        MedicationStatementResourceHandler,
    )
    from services.fhir_parsing.handlers.r4.medication_request_handler import (
        MedicationRequestResourceHandler,
    )
    from services.fhir_parsing.handlers.r4.procedure_handler import ProcedureResourceHandler

    from services.fhir_parsing.handlers.stu3.observation_handler import (
        StU3ObservationResourceHandler,
    )
    from services.fhir_parsing.handlers.stu3.condition_handler import (
        StU3ConditionResourceHandler,
    )
    from services.fhir_parsing.handlers.stu3.medication_request_handler import (
        StU3MedicationRequestResourceHandler,
    )

    from services.fhir_parsing.handlers.dstu2.observation_handler import (
        Dstu2ObservationResourceHandler,
    )
    from services.fhir_parsing.handlers.dstu2.condition_handler import (
        Dstu2ConditionResourceHandler,
    )
    from services.fhir_parsing.handlers.dstu2.procedure_handler import (
        Dstu2ProcedureResourceHandler,
    )
    from services.fhir_parsing.handlers.dstu2.medication_order_handler import (
        Dstu2MedicationOrderResourceHandler,
    )

    # Build singletons that get shared across version keys when the handler
    # is purely r4 logic (Patient, r4 Procedure).
    r4_patient = PatientResourceHandler()
    r4_procedure = ProcedureResourceHandler()

    handlers: dict[HandlerKey, AbstractResourceHandler] = {
        # --- r4 ---
        (FhirVersion.R4, FhirResourceType.PATIENT): r4_patient,
        (FhirVersion.R4, FhirResourceType.CONDITION): ConditionResourceHandler(),
        (FhirVersion.R4, FhirResourceType.OBSERVATION): ObservationResourceHandler(),
        (FhirVersion.R4, FhirResourceType.MEDICATION_STATEMENT): MedicationStatementResourceHandler(),
        (FhirVersion.R4, FhirResourceType.MEDICATION_REQUEST): MedicationRequestResourceHandler(),
        (FhirVersion.R4, FhirResourceType.PROCEDURE): r4_procedure,
        # --- stu3 ---
        (FhirVersion.STU3, FhirResourceType.PATIENT): r4_patient,
        (FhirVersion.STU3, FhirResourceType.CONDITION): StU3ConditionResourceHandler(),
        (FhirVersion.STU3, FhirResourceType.OBSERVATION): StU3ObservationResourceHandler(),
        (FhirVersion.STU3, FhirResourceType.MEDICATION_REQUEST): StU3MedicationRequestResourceHandler(),
        (FhirVersion.STU3, FhirResourceType.PROCEDURE): r4_procedure,
        # --- dstu2 ---
        (FhirVersion.DSTU2, FhirResourceType.PATIENT): r4_patient,
        (FhirVersion.DSTU2, FhirResourceType.CONDITION): Dstu2ConditionResourceHandler(),
        (FhirVersion.DSTU2, FhirResourceType.OBSERVATION): Dstu2ObservationResourceHandler(),
        (FhirVersion.DSTU2, FhirResourceType.MEDICATION_ORDER): Dstu2MedicationOrderResourceHandler(),
        (FhirVersion.DSTU2, FhirResourceType.PROCEDURE): Dstu2ProcedureResourceHandler(),
    }
    return ResourceHandlerRegistry(handlers)
