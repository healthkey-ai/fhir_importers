import abc

from entities.fhir.institution import Institution


class InstitutionRepository(abc.ABC):
    """Port for the Django-owned `fhir_institution` table. Read-only for the
    ETL — institutions are configured via Django admin."""

    @abc.abstractmethod
    def get_by_id(self, institution_id: int) -> Institution | None:
        raise NotImplementedError

    @abc.abstractmethod
    def get_by_slug(self, slug: str) -> Institution | None:
        raise NotImplementedError
