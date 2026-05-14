from typing import Any, Optional
import logging

import pandas as pd
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

_logger = logging.getLogger(__name__)


class BaseRepository:
    def __init__(self, engine: Engine):
        self._engine = engine

    def _select_as_df(self, query: str, **kwargs) -> pd.DataFrame:
        return pd.read_sql(query, self._engine, params=kwargs)

    def _select_one(self, query: str, **kwargs) -> Optional[dict[str, Any]]:
        with self._engine.begin() as connection:
            result = connection.execute(query, kwargs)
            item = result.fetchone()
            if not item:
                return None
            return dict(item)

    def _execute_and_scalar_one(self, query: str, **kwargs) -> Any:
        _logger.info("Query: %s", query)
        _logger.info("Params: %s", kwargs)
        with self._engine.begin() as connection:
            result = connection.execute(query, kwargs)
            return result.scalar_one()

    def _select_as_list(self, query: str, **kwargs) -> list:
        with self._engine.connect() as connection:
            result = connection.execute(query, **kwargs)
            return result.fetchall()

    def _execute(self, query: str, **kwargs) -> None:
        with self._engine.begin() as connection:
            result = connection.execute(query, kwargs)
            # print(result.rowcount)

    @staticmethod
    def _execute_and_scalar_one_conn(connection: Any, query: str, **kwargs: Any) -> Any:
        result = connection.execute(query, kwargs)
        return result.scalar_one()

    @staticmethod
    def _execute_conn(connection: Any, query: str, **kwargs: Any) -> None:
        connection.execute(query, kwargs)
