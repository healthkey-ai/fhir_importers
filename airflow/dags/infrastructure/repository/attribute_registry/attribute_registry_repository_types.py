import abc
from typing import Sequence

from typeguard import typechecked

from entities.trial_types import TrialRegister


class TrialAttributeRepositoryFilter(abc.ABC):
    """Abstract filter for trial attribute repository queries."""
    @abc.abstractmethod
    def get_where_sql(self) -> str:
        """Get the SQL WHERE clause for this filter."""
        raise NotImplementedError


class TrialAttributeRepositoryFilterList:
    """List of trial attribute repository filters."""
    @typechecked
    def __init__(self, filters: Sequence[TrialAttributeRepositoryFilter]):
        self._filters = filters

    def get_where_sql(self) -> str:
        """Get the combined SQL WHERE clause for all filters."""
        if not self._filters:
            return ""
        return "WHERE (" + ") AND (".join(_filter.get_where_sql() for _filter in self._filters) + ")"


class PendingInRegisterTrialAttributeRepositoryFilter(TrialAttributeRepositoryFilter):
    """Filter for pending attributes in a specific trial register."""
    @typechecked
    def __init__(self, register: TrialRegister):
        self._register = register

    def get_where_sql(self) -> str:
        return f"register = '{self._register.trial_db_code}'"
