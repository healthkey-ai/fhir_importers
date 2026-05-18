"""Run the FHIR ingestion pipeline against a local Bundle file.

Mirrors what the `fhir_ingest` Airflow DAG does, but reads the Bundle from
disk. Useful for one-off backfills and for exercising the pipeline without
the Airflow scheduler.

All infrastructure config (database DSN, S3 bucket, ...) is owned by the
`ServiceLocator` composition root. This script intentionally knows nothing
about environment variables.

Imports below rely on `PYTHONPATH=airflow/dags` (see `.env`); load that
before invoking, e.g. `source .env && python cli/fhir_ingest.py ...`, or
let your IDE / direnv load it for you.

Usage:
    python cli/fhir_ingest.py --file path/to/bundle.json [options]

Required:
    --file PATH                Path to a FHIR Bundle JSON file.

Optional:
    --fhir-version VERSION     One of r4 (default), stu3, dstu2.
    --provenance-source SRC    PATIENT_SELF, ADMIN_CORRECTION, EHR_SYNC,
                               or DOCUMENT_EXTRACTION.
    --provenance-source-user-id ID
                               String operator id stamped on every row.
    --provenance-target-patient-id ID
                               External patient id for analytics filtering.
    --provenance-organization-id N
    --provenance-modification-reason TEXT
                               Required when --provenance-source=ADMIN_CORRECTION.

Exit codes:
    0    Success.
    1    Pipeline failed (bad file, malformed JSON, invalid bundle, missing
         repository adapter, etc.). Reason is logged to stderr.
    2    Argparse usage error.
"""
import argparse
import json
import logging
from pathlib import Path

from entities.omop.provenance_record import ProvenanceSource
from services.fhir_parsing import FhirVersion, ProvenanceContext
from services.fhir_parsing.fhir_parsing_errors import FhirParsingError
from services.service_locator import ServiceLocator

_logger = logging.getLogger("cli.fhir_ingest")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fhir_ingest",
        description="Parse a FHIR Bundle and write its OMOP rows to the database.",
    )
    parser.add_argument(
        "--file",
        required=True,
        type=Path,
        help="Path to a FHIR Bundle JSON file.",
    )
    parser.add_argument(
        "--fhir-version",
        default=FhirVersion.R4.value,
        choices=[v.value for v in FhirVersion],
        help="FHIR version of the bundle (default: r4).",
    )
    parser.add_argument(
        "--provenance-source",
        default=None,
        choices=[s.value for s in ProvenanceSource],
        help="ProvenanceSource enum value stamped on every OMOP row.",
    )
    parser.add_argument("--provenance-source-user-id", default="", type=str)
    parser.add_argument("--provenance-target-patient-id", default=None, type=str)
    parser.add_argument("--provenance-organization-id", default=None, type=int)
    parser.add_argument(
        "--provenance-modification-reason",
        default=None,
        help="Required when --provenance-source=ADMIN_CORRECTION.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level (default: INFO).",
    )
    return parser.parse_args(argv)


def _build_provenance(args: argparse.Namespace) -> ProvenanceContext:
    source = (
        ProvenanceSource(args.provenance_source) if args.provenance_source else None
    )
    if source == ProvenanceSource.ADMIN_CORRECTION and not args.provenance_modification_reason:
        raise SystemExit(
            "--provenance-modification-reason is required when "
            "--provenance-source=ADMIN_CORRECTION"
        )
    return ProvenanceContext(
        source=source,
        source_user_id=args.provenance_source_user_id or "",
        target_patient_id=args.provenance_target_patient_id,
        organization_id=args.provenance_organization_id,
        modification_reason=args.provenance_modification_reason,
    )


def _load_bundle(file_path: Path) -> dict:
    if not file_path.exists():
        raise SystemExit(f"File not found: {file_path}")
    try:
        bundle = json.loads(file_path.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"Failed to parse {file_path} as JSON: {e}") from e
    if not isinstance(bundle, dict):
        raise SystemExit(f"{file_path} does not contain a JSON object")
    return bundle


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    bundle = _load_bundle(args.file)
    provenance = _build_provenance(args)
    fhir_version = FhirVersion(args.fhir_version)

    locator = ServiceLocator()

    try:
        service = locator.get_fhir_parsing_service()
    except NotImplementedError as e:
        _logger.error("Pipeline could not be built: %s", e)
        return 1

    try:
        result = service.ingest_from_bundle(
            bundle=bundle,
            fhir_version=fhir_version,
            provenance=provenance,
        )
    except FhirParsingError as e:
        _logger.error("Bundle rejected: %s", e)
        return 1

    print(json.dumps(result.model_dump(mode="json"), indent=2))
    _logger.info(
        "Done: created=%d updated=%d errors=%d patients=%d",
        result.created_count,
        result.updated_count,
        len(result.errors),
        len(result.patients),
    )
    # Per-patient failures are captured in `result.errors` rather than raised,
    # so the CLI surfaces them via a non-zero exit code for scripts.
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
