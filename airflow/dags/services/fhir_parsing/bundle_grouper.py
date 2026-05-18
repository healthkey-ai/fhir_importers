import logging
from typing import Any

from services.fhir_parsing.fhir_parsing_errors import InvalidBundleError
from services.fhir_parsing.fhir_parsing_types import FhirResourceType

_logger = logging.getLogger(__name__)

PatientBuckets = dict[str, list[dict[str, Any]]]
GroupedBundle = dict[str, PatientBuckets]


class BundleGrouper:
    """Splits a FHIR Bundle into per-patient buckets keyed by resourceType.

    No FHIR parsing happens here — this is a pure routing step so each per-resource
    handler can focus on a single resource type.
    """

    def group_by_patient(self, bundle: dict[str, Any]) -> GroupedBundle:
        if bundle.get("resourceType") != "Bundle":
            raise InvalidBundleError("FHIR document must be a Bundle")

        grouped: GroupedBundle = {}
        for entry in bundle.get("entry", []) or []:
            resource = entry.get("resource") or {}
            resource_type = resource.get("resourceType")
            if not resource_type:
                continue

            patient_id = self._extract_patient_id(resource, resource_type)
            if not patient_id:
                _logger.debug(
                    "Skipping %s resource with no patient reference", resource_type
                )
                continue

            buckets = grouped.setdefault(patient_id, {})
            buckets.setdefault(resource_type, []).append(resource)

        return grouped

    @staticmethod
    def _extract_patient_id(resource: dict[str, Any], resource_type: str) -> str | None:
        if resource_type == FhirResourceType.PATIENT.value:
            return resource.get("id")
        ref = (resource.get("subject") or {}).get("reference", "")
        if "/" in ref:
            return ref.split("/")[-1]
        return None
