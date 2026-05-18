import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

import infrastructure.repository.omop.concept.sql as sql
from entities.omop.concept import Concept
from infrastructure.repository.base_repository import BaseRepository
from infrastructure.repository.omop.concept.repository import ConceptRepository

_logger = logging.getLogger(__name__)


class ConceptRepositoryImplementation(ConceptRepository, BaseRepository):
    """Raw SQL adapter for OMOP `concept` lookups. Read-only for ingestion."""

    def __init__(self, engine: Engine):
        super().__init__(engine)
        self._engine = engine
        self._id_cache: dict[int, Concept | None] = {}
        self._code_cache: dict[tuple[str, str], Concept | None] = {}

    def get_by_id(self, concept_id: int) -> Concept | None:
        if concept_id in self._id_cache:
            return self._id_cache[concept_id]
        row = self._select_one(text(sql.SELECT_BY_ID), concept_id=concept_id)
        result = _row_to_concept(row)
        self._id_cache[concept_id] = result
        return result

    def find_by_code(self, code: str, vocabulary_id: str) -> Concept | None:
        key = (code, vocabulary_id)
        if key in self._code_cache:
            return self._code_cache[key]
        row = self._select_one(text(sql.SELECT_BY_CODE), code=code, vocabulary_id=vocabulary_id)
        result = _row_to_concept(row)
        self._code_cache[key] = result
        return result

    def find_by_name(self, name_substring: str) -> Concept | None:
        if not name_substring:
            return None
        # PG LIKE wildcard escapes are not needed for our use; the substring
        # comes from FHIR display text and is short (<= 50 chars by Django
        # `*_source_value` limits).
        return _row_to_concept(
            self._select_one(text(sql.SELECT_BY_NAME_LIKE), pattern=f"%{name_substring}%")
        )


def _row_to_concept(row) -> Concept | None:
    if row is None:
        return None
    return Concept(
        concept_id=int(row["concept_id"]),
        concept_name=row["concept_name"],
        concept_code=row["concept_code"],
        vocabulary_id=row["vocabulary_id"],
    )
