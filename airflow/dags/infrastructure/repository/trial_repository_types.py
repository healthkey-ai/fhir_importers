import abc
from typing import Sequence

from typeguard import typechecked

from entities.disease import Disease
from entities.trial_types import TrialRegister
import infrastructure.repository.trial_repository_sql as trial_repository_sql


class TrialRepositoryFilter(abc.ABC):
    @abc.abstractmethod
    def get_where_sql(self) -> str:
        raise NotImplementedError


class TrialRepositoryFilterList:
    @typechecked
    def __init__(self, filters: Sequence[TrialRepositoryFilter]):
        self._filters = filters

    def get_where_sql(self) -> str:
        if not self._filters:
            return "true"
        return "(" + ") AND (".join(_filter.get_where_sql() for _filter in self._filters) + ")"

class PkTrialRepositoryFilter(TrialRepositoryFilter):
    @typechecked
    def __init__(self, pks: Sequence[int]):
        self._pks = pks

    def get_where_sql(self) -> str:
        values = ", ".join([str(pk) for pk in self._pks])
        return f"id IN ({values})"


class NaturalIdTrialRepositoryFilter(TrialRepositoryFilter):
    @typechecked
    def __init__(self, natural_ids: Sequence[str]):
        self._natural_ids = natural_ids

    def get_where_sql(self) -> str:
        values = ", ".join([f"'{nid}'" for nid in self._natural_ids])
        return f"study_id IN ({values})"


class DiseaseTrialRepositoryFilter(TrialRepositoryFilter):
    @typechecked
    def __init__(self, disease: Disease):
        self.disease = disease

    def get_where_sql(self) -> str:
        return f"disease = '{self.disease.value}'"


class CountryTrialRepositoryFilter(TrialRepositoryFilter):
    @typechecked
    def __init__(self, countries: Sequence[str]):
        self._countries = countries

    def get_where_sql(self) -> str:
        raise NotImplementedError


class TrialRegisterTrialRepositoryFilter(TrialRepositoryFilter):
    @typechecked
    def __init__(self, registers: Sequence[TrialRegister]):
        self._registers = registers

    def get_where_sql(self) -> str:
        values = ", ".join([f"'{r.trial_db_code}'" for r in self._registers])
        return f"register IN ({values})"


class TrialUniverseRepositoryFilter(TrialRepositoryFilter):
    @typechecked
    def __init__(self, universes: list[str]):
        self._universes = universes

    def get_where_sql(self) -> str:
        causes = list()
        for universe in self._universes:
            code_in = self._get_universe_code_in_sql(universe)
            causes.append(f"study_id IN ({code_in})")
        return "(" + ") OR (".join(causes) + ")"

    def _get_universe_code_in_sql(self, universe: str) -> str:
        if universe == "breast_cancer_100":
            return self._get_breast_cancer_100_study_ids()
        if universe == "multiple_myeloma_100":
            return self._get_multiple_myeloma_100_study_ids()
        if universe == "multiple_myeloma_uk_50":
            return self._get_multiple_myeloma_uk_50_study_ids()
        if universe == "wrong_value":
            return self._get_wrong_value_sql()
        if universe == "testing_260121":
            from universe.testing_260121 import testing_260121_universe
            values = ", ".join([f"'{x}'" for x in testing_260121_universe])
            return values
        raise NotImplementedError

    @staticmethod
    def _get_breast_cancer_100_study_ids() -> str:
        from universe.breast_cancer import breast_universe
        values = ", ".join([f"'{x}'" for x in breast_universe])
        return values

    @staticmethod
    def _get_multiple_myeloma_100_study_ids() -> str:
        from universe.multiple_myeloma_100 import multiple_myeloma_100
        values = ", ".join([f"'{x}'" for x in multiple_myeloma_100])
        return values

    @staticmethod
    def _get_multiple_myeloma_uk_50_study_ids() -> str:
        from universe.multiple_myeloma_uk_50 import multiple_myeloma_uk_50
        values = ", ".join([f"'{x}'" for x in multiple_myeloma_uk_50])
        return values

    @staticmethod
    def _get_wrong_value_sql() -> str:
        return trial_repository_sql.WHERE_UNIVERSE_WRONG_VALUE


class SqlHackTrialRepositoryFilter(TrialRepositoryFilter):
    @typechecked
    def __init__(self, sql_where: str):
        self._sql_where = sql_where

    def get_where_sql(self) -> str:
        return self._sql_where
