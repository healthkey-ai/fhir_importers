from enum import StrEnum

DagRunId = str

TaskId = str


class AirflowDag(StrEnum):
    TRIAL_ADMIN_TEST_EXTRACT = "trial_admin_test_extract"
    TRIAL_EXTRACT = "trial_extract"
    TRIAL_EXTRACT_NIGHTLY = "trial_extract_nightly"
    REGISTRY_EXTRACT = "registry_extract"
    TRIAL_EXTRACT_SCHEDULE_OF_ASSESSMENT = "trial_extract_schedule_of_assessment"
    FHIR_INGEST = "fhir_ingest"
    FHIR_EXTRACT = "fhir_extract"
    FHIR_BULK_EXTRACT = "fhir_bulk_extract"


class AirflowDagRunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SCHEDULED = "scheduled"

    def is_finished(self) -> bool:
        return self.is_done() or self.is_failed()

    def is_done(self) -> bool:
        return self in (
            AirflowDagRunState.SUCCESS,
        )

    def is_failed(self) -> bool:
        return self in (
            AirflowDagRunState.FAILED,
            AirflowDagRunState.CANCELLED,
        )
