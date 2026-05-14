import abc

import pandas as pd

from entities.trial_raw_data import TrialRawData
from entities.trial_types import TrialRegister, TrialNaturalId


class RawDataRepository(abc.ABC):
    @abc.abstractmethod
    def get_df(self, register: TrialRegister | None = None) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def select(self, register: TrialRegister, limit: int, offset: int) -> list[TrialRawData]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_by_natural_id(self, natural_id: TrialNaturalId) -> TrialRawData | None:
        raise NotImplementedError

    @abc.abstractmethod
    def create_or_update(self, item: TrialRawData) -> None:
        raise NotImplementedError
