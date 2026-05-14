import json
import logging
from typing import Dict, Any, Collection

import pandas as pd
from sqlalchemy import text

from entities.disease import Disease
from entities.trial import Trial
from entities.trial_types import TrialNaturalId
from infrastructure.repository.base_repository import BaseRepository
import infrastructure.repository.trial_repository_sql as trial_repository_sql
from infrastructure.repository.trial_repository_types import (
    TrialRepositoryFilterList,
)

_logger = logging.getLogger(__name__)

trial_defaults = {
    # Required text/char fields
    "code": "",  # unique
    "study_id": "",
    "register": "",
    "brief_title": "",
    "official_title": "",
    "intervention_treatments_text": "",
    "sponsor_name": "",
    "contact_email": "",
    "link": "",
    "recruitment_status": "",
    "study_type": "",

    # Required booleans
    "is_validated": False,
    "is_labeled": False,

    # JSONFields (Django sets default to list())
    "locations_name": [],
    "intervention_treatments": [],
    "researchers": [],
    "researchers_emails": [],
    "phases": [],
    "stages": [],
    "therapies_required": [],
    "therapies_excluded": [],
    "therapy_types_required": [],
    "therapy_types_excluded": [],
    "therapy_components_required": [],
    "therapy_components_excluded": [],
    "supportive_therapies_required": [],
    "supportive_therapies_excluded": [],
    "planned_therapies_required": [],
    "planned_therapies_excluded": [],
    "pre_existing_conditions_excluded": [],
    "cytogenic_markers_required": [],
    "cytogenic_markers_all": [],
    "cytogenic_markers_excluded": [],
    "molecular_markers_required": [],
    "molecular_markers_excluded": [],
    "stem_cell_transplant_history": [],
    "histologic_types_required": [],
    "estrogen_receptor_statuses_required": [],
    "progesterone_receptor_statuses_required": [],
    "her2_statuses_required": [],
    "hrd_statuses_required": [],
    "hr_statuses_required": [],
    "tumor_stages_required": [],
    "tumor_stages_excluded": [],
    "nodes_stages_required": [],
    "nodes_stages_excluded": [],
    "distant_metastasis_stages_required": [],
    "distant_metastasis_stages_excluded": [],
    "staging_modalities_required": [],
    "mutation_genes_required": [],
    "mutation_variants_required": [],
    "mutation_origins_required": [],
    "mutation_interpretations_required": [],
    "languages_skills_required": [],
    "ethnicity_required": [],
    "disease_activities_required": [],

    # Numeric defaults (set to 0 unless nullable in model)
    "enrollment_count": 0,
    "patient_burden_score": 0,
    "risk_score": 0,
    "benefit_score": 0,

    "binet_stages_required": [],
    "protein_expressions_required": [],
    "protein_expressions_excluded": [],
    "richter_transformations_required": [],
    "richter_transformations_excluded": [],
    "tumor_burdens_required": [],
}


class TrialRepository(BaseRepository):
    _table_name: str = "trials_trial"

    def get_df_v2(self, filters: TrialRepositoryFilterList, limit: int, offset: int = 0) -> pd.DataFrame:
        where = filters.get_where_sql()
        query = text(trial_repository_sql.SELECT_ALL_DYNAMIC_WHERE.format(where=where))
        params = {"limit": limit, "offset": offset}
        _logger.info("get_df_v2 query '''%s''' params %s", query, params)
        return self._select_as_df(query, **params)

    def get_df(self) -> pd.DataFrame:
        """
        ToDo: deprecate it
        """
        query = f"SELECT * FROM {self._table_name};"
        return self._select_as_df(query)

    def update(self, surrogate_id: int, data: Dict[str, Any]) -> None:
        if not data:
            raise ValueError("No data to update")

        params = {"id": surrogate_id}
        sql_set = []
        for key, value in data.items():
            if isinstance(value, list):
                params[key] = json.dumps(value)
            else:
                params[key] = value
            sql_set.append(f"{key} = :{key}")

        query = text(f"""UPDATE {self._table_name}
        SET """ + ", ".join(sql_set) + """, updated_at = NOW()
        WHERE id = :id;""")
        _logger.info(f"Executing query: {query}, params: {params}")
        with self._engine.connect() as connection:
            connection.execute(query, **params)

    def upsert_single(self, trial: Trial) -> int:
        params = {}
        sql_set_insert = []
        sql_set_update = []
        insert_columns = []

        for key, value in {**trial_defaults, **trial.values}.items():
            if key in ("id", "created_at", "updated_at"):
                continue
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            else:
                assert isinstance(value, (str, int, float, bool)) or value is None, \
                    f"Unsupported type for key '{key}': {type(value)} '{value}'"
            params[key] = value
            insert_columns.append(key)
            if key not in ("code",):
                if key in trial.values:
                    sql_set_update.append(f"{key} = :{key}")
        params["study_id"] = trial.natural_id
        params["code"] = trial.generate_code()

        query = text(f"""
            INSERT INTO {self._table_name} ({', '.join(insert_columns)}, created_at, updated_at)
            VALUES ({', '.join(':' + key for key in insert_columns)}, NOW(), NOW())
            ON CONFLICT (code) DO UPDATE
            SET {', '.join(sql_set_update)}, updated_at = NOW()
            RETURNING id;
        """)
        _logger.info("Executing query: %s, params: %s", query, params)
        return self._execute_and_scalar_one(query, **params)

    def upsert_many(self, trials: Collection[Trial]) -> None:
        """
        Not being used in production, so not optimized for bulk insert yet.
        """
        for trial in trials:
            try:
                self.upsert_single(trial)
            except Exception as e:
                raise RuntimeError(f"Failed to upsert trial {trial.natural_id=}") from e

    def create(self, natural_id: TrialNaturalId) -> None:
        """
        ToDo: deprecate it
        """
        query = text(f"INSERT INTO {self._table_name} (study_id) VALUES (:study_id);")
        _logger.info(f"Executing query: {query}, data: {natural_id}")
        with self._engine.connect() as connection:
            connection.execute(query, study_id=natural_id)

    def get_by_natural_id(self, natural_id: TrialNaturalId) -> Trial | None:
        query = text(f"SELECT * FROM {self._table_name} WHERE study_id = :study_id;")
        params = {"study_id": natural_id}
        data = self._select_one(query, **params)
        if not data:
            return None
        return Trial(
            pk=data["id"],
            natural_id=data["study_id"],
            values=data,
        )

    def get_by_code(self, natural_id: TrialNaturalId) -> Trial | None:
        query = text(f"SELECT * FROM {self._table_name} WHERE code = :code;")
        params = {"code": natural_id}
        data = self._select_one(query, **params)
        if not data:
            return None
        return Trial(
            pk=data["id"],
            natural_id=data["study_id"],
            values=data,
        )

    def get_by_natural_id_and_disease(self, disease: Disease, natural_id: TrialNaturalId) -> Trial | None:
        query = text(f"SELECT * FROM {self._table_name} WHERE study_id = :study_id AND disease = :disease;")
        params = {
            "study_id": natural_id,
            "disease": disease.value,
        }
        data = self._select_one(query, **params)
        if not data:
            return None
        return Trial(
            pk=data["id"],
            natural_id=data["study_id"],
            values=data,
        )

    def filter_by_natural_ids(self, natural_ids: Collection[TrialNaturalId]) -> pd.DataFrame:
        if not natural_ids:
            return pd.DataFrame()
        placeholders = ', '.join([':id' + str(i) for i in range(len(natural_ids))])
        query = text(f"SELECT * FROM {self._table_name} WHERE study_id IN ({placeholders})")
        params = {f'id{i}': natural_id for i, natural_id in enumerate(natural_ids)}
        return self._select_as_df(query, **params)

    def get_labels_by_pk(self, pk: int) -> pd.DataFrame:
        query = text(f"SELECT attr_name, labeled_value FROM trials_triallabeledvalue  WHERE trial_id = :id;")
        params = {"id": pk}
        return self._select_as_df(query, **params)

    def get_labels_by_natural_id(self, natural_id: TrialNaturalId) -> pd.DataFrame:
        trial = self._select_one(f"SELECT id FROM {self._table_name} WHERE study_id = :study_id;", study_id=natural_id)
        if not trial:
            _logger.error(f"Trial with natural ID {natural_id} not found.")
            return pd.DataFrame()
        return self.get_labels_by_pk(trial['id'])
