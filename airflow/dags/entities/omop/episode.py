from dataclasses import dataclass
from datetime import date


@dataclass
class Episode:
    episode_id: int | None = None
    person_id: int | None = None
    episode_concept_id: int | None = None
    episode_object_concept_id: int | None = None
    episode_type_concept_id: int | None = None
    episode_start_date: date | None = None
    episode_end_date: date | None = None
    episode_number: int | None = None
    episode_source_value: str | None = None
