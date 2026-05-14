import abc

from typing import Sequence
import pandas as pd

from entities.attribute import AttributeRegistryStatus
from infrastructure.repository.attribute_registry.attribute_registry_repository_types import (
    TrialAttributeRepositoryFilterList
)


class AttributeRegistryRepository(abc.ABC):
    """Abstract repository for attribute registry status."""
    @abc.abstractmethod
    def fetch_v2(self, filters: TrialAttributeRepositoryFilterList, limit: int, offset: int = 0) -> pd.DataFrame:
        """Fetch attribute registry status with filters, limit, and offset."""
        raise NotImplementedError

    @abc.abstractmethod
    def fetch(
        self,
        filter_registry: str | None = None,
        filter_is_extracted: bool | None = None,
    ) -> list[AttributeRegistryStatus]:
        """Fetch attribute registry status with optional filters."""
        raise NotImplementedError

    @abc.abstractmethod
    def update_is_extracted(self, registry: str, attributes: Sequence[str]) -> None:
        """Update the is_extracted status for given attributes in a registry."""
        raise NotImplementedError
