import logging

from typing import Sequence
from sqlalchemy import text
import pandas as pd

from entities.attribute import AttributeRegistryStatus
from entities.trial_types import TrialRegister
from infrastructure.repository.attribute_registry import sql
from infrastructure.repository.base_repository import BaseRepository
from infrastructure.repository.attribute_registry.attribute_registry_repository_types import \
    TrialAttributeRepositoryFilterList
from infrastructure.repository.attribute_registry.attribute_registry_repository import AttributeRegistryRepository

_logger = logging.getLogger(__name__)

DEFAULT_REGISTER = TrialRegister.CLINICAL_TRIALS_GOV


class AttributeRegistryRepositoryImplementation(AttributeRegistryRepository, BaseRepository):
    """Concrete implementation of AttributeRegistryRepository."""

    def fetch_v2(self, filters: TrialAttributeRepositoryFilterList | None, limit: int, offset: int = 0) -> pd.DataFrame:
        # normalize filters
        if filters is None:
            # No filters → no WHERE clause
            where_sql = ""
        else:
            # filters is a list of filter CLASSES → instantiate with no args
            where_sql = filters.get_where_sql()

        query = sql.FETCH_TRIAL_ATTRIBUTES_V2.format(where=where_sql)
        params = {"limit": limit, "offset": offset}
        return self._select_as_df(text(query), **params)

    def fetch(
            self,
            filter_registry: str | None = None,
            filter_is_extracted: bool | None = None,
    ) -> list[AttributeRegistryStatus]:
        """
        ToDo: deprecate it
        """
        # Build query
        query = text(sql.FETCH_TRIAL_ATTRIBUTES)

        # Execute query using named parameters
        df = self._select_as_df(
            query,
            registry=filter_registry,
            is_extracted=filter_is_extracted,
        )

        result: list[AttributeRegistryStatus] = []
        for _, row in df.iterrows():
            result.append(
                AttributeRegistryStatus(
                    registry=row["register"],
                    attribute=row["attribute"],
                    is_extracted=row["is_extracted"],
                )
            )
        return result

    def update_is_extracted(self, registry: str, attributes: Sequence[str]) -> None:
        query = text(sql.UPDATE_IS_EXTRACTED)
        self._execute(query, registry=registry, attributes=tuple(attributes))
