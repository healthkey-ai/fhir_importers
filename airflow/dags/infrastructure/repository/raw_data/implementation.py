import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

import infrastructure.repository.raw_data.sql as sql
from entities.trial_raw_data import TrialRawData
from entities.trial_types import TrialNaturalId, TrialRegister
from infrastructure.repository.base_repository import BaseRepository
from infrastructure.repository.raw_data.repository import RawDataRepository


class RawDataRepositoryImplementation(RawDataRepository, BaseRepository):
    _table_name: str = "trials_rawdataitem"

    def __init__(self, engine: Engine):
        super().__init__(engine)
        self._engine = engine

    def get_df(self, register: TrialRegister | None = None) -> pd.DataFrame:
        params = {
            "limit": 100_000,
            "offset": 0,
        }
        if register is None:
            query = text(sql.SELECT_ALL)
        else:
            query = text(sql.SELECT_REGISTER)
            params["source_name"] = register.value
        return self._select_as_df(query, **params)

    def select(self, register: TrialRegister, limit: int, offset: int) -> list[TrialRawData]:
        params = {
            "limit": limit,
            "offset": offset,
        }
        if register is None:
            query = text(sql.SELECT_ALL)
        else:
            query = text(sql.SELECT_REGISTER)
            params["source_name"] = register.value
        data = self._select_as_df(query, **params)
        result = list()
        for _, row in data.iterrows():
            result.append(
                TrialRawData(
                    natural_id=row["record_id"],
                    registry=TrialRegister.from_raw_data_db_code(row["source_name"]),
                    raw_data=row["raw_data"],
                )
            )
        return result

    def get_by_natural_id(self, natural_id: TrialNaturalId) -> TrialRawData | None:
        query = text(sql.SELECT_BY_NATURAL_ID)
        params = {"record_id": natural_id}
        data = self._select_one(query, **params)
        if data is None:
            return None
        return TrialRawData(
            natural_id=data["record_id"],
            registry=TrialRegister(data["source_name"]),
            raw_data=data["raw_data"],
        )

    def create_or_update(self, item: TrialRawData) -> None:
        query = text(sql.INSERT_OR_UPDATE)
        params = {
            "record_id": item.natural_id,
            "source_name": item.registry.value,
            "raw_data": item.raw_data,
        }
        self._execute(query, **params)
