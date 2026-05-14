import json
import logging
from typing import TYPE_CHECKING, Any

import pandas as pd
from sqlalchemy import text

from infrastructure.repository.base_repository import BaseRepository

if TYPE_CHECKING:
    from services.trial_parsing.parsers.abstract_trial_parser import ParsedTrialLocation
    from entities.trial import Trial


_logger = logging.getLogger(__name__)

_GET_LOCATIONS_SQL = text("""
SELECT l.id, l.title, l.city, s.title AS state, c.title AS country
FROM trials_location l
JOIN trials_country c ON l.country_id = c.id
JOIN trials_state s ON l.state_id = s.id;
""")

_UPSERT_COUNTRY_SQL = text("""
INSERT INTO trials_country (title, created_at, updated_at)
VALUES (:title, NOW(), NOW())
ON CONFLICT (title) DO UPDATE SET updated_at = NOW()
RETURNING id;
""")

_UPSERT_STATE_SQL = text("""
INSERT INTO trials_state (title, country_id, created_at, updated_at)
VALUES (:title, :country_id, NOW(), NOW())
ON CONFLICT (title, country_id) DO UPDATE SET updated_at = NOW()
RETURNING id;
""")

_UPSERT_LOCATION_SQL = text("""
INSERT INTO trials_location (title, city, state_id, country_id, created_at, updated_at, geo_point)
VALUES (:title, :city, :state_id, :country_id, NOW(), NOW(), ST_GeomFromText(:geo_point, 4326))
ON CONFLICT (title) DO UPDATE SET updated_at = NOW(), geo_point = ST_GeomFromText(:geo_point, 4326)
RETURNING id;
""")


_UPSERT_TRIAL_LOCATION_SQL = text("""
INSERT INTO trials_locationtrial (trial_id, location_id, created_at, updated_at, is_recruiting, location_contacts, recruitment_status)
VALUES (:trial_id, :location_id, NOW(), NOW(), :is_recruiting, :location_contacts, :recruitment_status)
ON CONFLICT (trial_id, location_id)
  DO UPDATE
  SET updated_at = NOW(),
  is_recruiting = :is_recruiting,
  recruitment_status = :recruitment_status,
  location_contacts = :location_contacts;
""")


def _location_to_sql_params(location: "ParsedTrialLocation") -> dict[str, Any]:
    """Convert ParsedTrialLocation to SQL params for location upsert (without country/state IDs)."""
    title_parts = [p for p in [location.city, location.state, location.country] if p]

    if location.geo_point is None:
        geo_point = None
    else:
        geo_point = f"POINT({location.geo_point.longitude} {location.geo_point.latitude})"

    if location.contacts:
        contacts_json = json.dumps([
            {"email": x.email, "full_name": x.full_name}
            for x in location.contacts
        ])
    else:
        contacts_json = "[]"

    return {
        "title": ", ".join(title_parts),
        "city": location.city,
        "geo_point": geo_point,
        "is_recruiting": location.recruitment_status == "RECRUITING",
        "recruitment_status": location.recruitment_status,
        "location_contacts": contacts_json,
    }


class LocationRepository(BaseRepository):
    def get_df(self) -> pd.DataFrame:
        return self._select_as_df(_GET_LOCATIONS_SQL)

    def sync_trial_locations_bulk(
        self,
        trial_id: int,
        trial: "Trial",
        locations: list["ParsedTrialLocation"],
    ) -> list[int]:
        """Upsert all locations and link them to the trial in a single transaction."""
        country_cache: dict[str, int] = {}
        state_cache: dict[tuple[str, int], int] = {}
        location_ids: list[int] = []
        fallback_recruitment_status = trial.values["recruitment_status"]

        with self._engine.begin() as conn:
            for location in locations:
                params = _location_to_sql_params(location)

                # Upsert country (with cache)
                if location.country in country_cache:
                    country_id = country_cache[location.country]
                else:
                    country_id = self._execute_and_scalar_one_conn(
                        conn, _UPSERT_COUNTRY_SQL, title=location.country,
                    )
                    country_cache[location.country] = country_id

                # Upsert state (with cache)
                if location.state:
                    state_key = (location.state, country_id)
                    if state_key in state_cache:
                        state_id = state_cache[state_key]
                    else:
                        state_id = self._execute_and_scalar_one_conn(
                            conn, _UPSERT_STATE_SQL, title=location.state, country_id=country_id,
                        )
                        state_cache[state_key] = state_id
                else:
                    state_id = None

                # Upsert location
                location_id = self._execute_and_scalar_one_conn(
                    conn, _UPSERT_LOCATION_SQL,
                    title=params["title"], city=params["city"],
                    state_id=state_id, country_id=country_id,
                    geo_point=params["geo_point"],
                )
                location_ids.append(location_id)

                # Upsert trial-location link
                self._execute_conn(
                    conn, _UPSERT_TRIAL_LOCATION_SQL,
                    trial_id=trial_id,
                    location_id=location_id,
                    is_recruiting=params["is_recruiting"],
                    recruitment_status=params["recruitment_status"] or fallback_recruitment_status,
                    location_contacts=params["location_contacts"],
                )

        return location_ids
