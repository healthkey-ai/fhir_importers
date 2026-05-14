import logging

from sqlalchemy import text

from entities.attribute import TrialAttribute, TrialAttributeList, TrialAttributeFactory
from infrastructure.repository.base_repository import BaseRepository

_logger = logging.getLogger(__name__)


class AttributeRepository(BaseRepository):
    _table_name = "trials_fieldparticipationrequirement"

    def fetch_all(self) -> TrialAttributeList:
        """
        Fetch all attributes from the database.
        :return: TrialAttributeList containing all attributes.
        """
        return self.fetch()

    def fetch(self, filter_name: set[str] | None = None) -> TrialAttributeList:
        query = text(f"SELECT attr_name, prompt FROM {self._table_name};")
        data = self._select_as_list(query)
        result = list()
        for row in data:
            if row[0] == 'prompts':
                # ToDo: Remove this test line
                continue

            # Apply filter
            if filter_name is not None and row[0] not in filter_name:
                continue

            # Parse row
            try:
                # Note: trial=None is acceptable here as we're creating attribute templates
                attribute = TrialAttributeFactory.create(name=row[0], prompt=row[1], trial=None)
            except Exception as e:
                raise ValueError(f"Error parsing row {row}") from e
            _logger.info(f"Attribute {row[0]} has type {type(attribute)}")
            assert attribute.response_type is not None
            result.append(attribute)
        return TrialAttributeList(attributes=result)
