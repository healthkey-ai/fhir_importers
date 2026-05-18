import abc

from entities.omop.provenance_record import ProvenanceRecord


class ProvenanceRepository(abc.ABC):
    """Port for the audit-trail `provenance_record` table.

    The Django schema uses a generic foreign key (`content_type_id` joined to
    `django_content_type` + `object_id`). The repository resolves the
    `content_type_id` from a (`app_label`, `model`) tuple supplied on the
    entity — callers don't need to know Django ContentType ids.
    """

    @abc.abstractmethod
    def create(self, record: ProvenanceRecord) -> ProvenanceRecord:
        raise NotImplementedError
