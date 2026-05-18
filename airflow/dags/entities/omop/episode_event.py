from dataclasses import dataclass


@dataclass
class EpisodeEvent:
    id: int | None = None
    episode_id: int | None = None
    event_id: int | None = None
    episode_event_field_concept_id: int | None = None
