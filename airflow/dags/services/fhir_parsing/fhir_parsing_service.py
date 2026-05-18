import logging
from typing import Any

from services.artifact import ArtifactKey, ArtifactService
from services.fhir_parsing.bundle_grouper import BundleGrouper, GroupedBundle
from services.fhir_parsing.fhir_parsing_errors import (
    FhirParsingError,
    UnsupportedResourceTypeError,
)
from services.fhir_parsing.fhir_parsing_types import (
    FhirIngestionResult,
    FhirPatientIngestionResult,
    FhirResourceType,
    FhirVersion,
    ParsedPatientPayload,
    ParsedPerson,
    ProvenanceContext,
)
from services.fhir_parsing.handlers.registry import ResourceHandlerRegistry
from services.fhir_parsing.writers.abstract_omop_writer import AbstractOmopWriter

_logger = logging.getLogger(__name__)


class FhirParsingService:
    """Async-job entry point for FHIR bundle ingestion.

    Triggered by an Airflow DAG (which itself is triggered by the Django
    `upload_fhir` endpoint). The DAG passes an ArtifactKey + FhirVersion +
    ProvenanceContext in its run conf; this service downloads the staged
    bundle, dispatches each resource to a per-version per-resourceType
    handler, and writes the resulting OMOP rows through the injected writer.
    """

    def __init__(
        self,
        artifact_service: ArtifactService,
        bundle_grouper: BundleGrouper,
        handler_registry: ResourceHandlerRegistry,
        omop_writer: AbstractOmopWriter,
    ):
        self._artifact_service = artifact_service
        self._bundle_grouper = bundle_grouper
        self._handler_registry = handler_registry
        self._omop_writer = omop_writer

    def ingest_from_artifact(
        self,
        artifact_key: ArtifactKey,
        fhir_version: FhirVersion,
        provenance: ProvenanceContext,
    ) -> FhirIngestionResult:
        bundle = self._artifact_service.download_json(artifact_key)
        if not isinstance(bundle, dict):
            raise FhirParsingError(
                f"Artifact {artifact_key} does not contain a JSON object"
            )
        return self.ingest_from_bundle(bundle, fhir_version, provenance)

    def ingest_from_bundle(
        self,
        bundle: dict[str, Any],
        fhir_version: FhirVersion,
        provenance: ProvenanceContext,
    ) -> FhirIngestionResult:
        grouped: GroupedBundle = self._bundle_grouper.group_by_patient(bundle)
        result = FhirIngestionResult()

        for fhir_patient_id, buckets in grouped.items():
            try:
                payload = self._build_payload(fhir_patient_id, fhir_version, buckets)
                patient_result = self._omop_writer.write_patient(payload, provenance)
                result.patients.append(patient_result)
                if patient_result.is_new:
                    result.created_count += 1
                else:
                    result.updated_count += 1
            except Exception as e:
                _logger.exception("Failed to ingest patient %s", fhir_patient_id)
                result.errors.append(f"Patient {fhir_patient_id}: {e}")
                result.patients.append(
                    FhirPatientIngestionResult(
                        fhir_patient_id=fhir_patient_id,
                        error=str(e),
                    )
                )

        return result

    def _build_payload(
        self,
        fhir_patient_id: str,
        fhir_version: FhirVersion,
        buckets: dict[str, list[dict[str, Any]]],
    ) -> ParsedPatientPayload:
        payload = ParsedPatientPayload(person=ParsedPerson(fhir_id=fhir_patient_id))

        # Patient resource first so demographics are set before observations/
        # conditions that may reference them.
        ordered_types = sorted(
            buckets.keys(),
            key=lambda t: 0 if t == FhirResourceType.PATIENT.value else 1,
        )
        for resource_type_str in ordered_types:
            try:
                resource_type = FhirResourceType(resource_type_str)
            except ValueError:
                _logger.debug(
                    "Skipping unknown resourceType %s for patient %s",
                    resource_type_str,
                    fhir_patient_id,
                )
                continue

            if not self._handler_registry.has(fhir_version, resource_type):
                _logger.debug(
                    "No handler for %s/%s; skipping", fhir_version, resource_type
                )
                continue

            handler = self._handler_registry.get(fhir_version, resource_type)
            for resource in buckets[resource_type_str]:
                try:
                    handler.handle(resource, payload)
                except UnsupportedResourceTypeError:
                    raise
                except Exception:
                    _logger.exception(
                        "Handler %s failed on resource %s",
                        type(handler).__name__,
                        resource.get("id"),
                    )
                    raise

        return payload
