import abc
import logging

import pandas as pd

_logger = logging.getLogger(__name__)


class AttributeOptionsRepository(abc.ABC):
    @abc.abstractmethod
    def get_therapy_components_by_disease_codes(self, disease_codes: tuple[str, ...]) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_therapies_by_disease_codes(self, disease_codes: tuple[str, ...]) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_therapy_types(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_pre_existing_condition_categories(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_cytogenic_markers(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_molecular_markers(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_brca1_mutations(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_brca1_interpretations(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_brca2_mutations(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_brca2_interpretations(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_pik3ca_mutations(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_pik3ca_interpretations(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_tp53_mutations(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_tp53_interpretations(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_esr1_mutations(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_esr1_interpretations(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_estrogen_receptor_status_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_progesterone_receptor_status_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_her2_status_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_histologic_type_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_hrd_status_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_hr_status_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_mutation_gene_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_mutation_variant_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_mutation_interpretation_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_mutation_origin_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_trial_type_options(self, disease_code: str) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_tumor_stage_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_node_stage_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_metastasis_stage_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_modality_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_toxicity_grade_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_language_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_language_skill_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_planned_therapy_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_language_skill_product_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_binet_stage_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_protein_expression_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_richter_transformation_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_tumor_burden_options(self) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_trial_purpose_options(self) -> pd.DataFrame:
        raise NotImplementedError
