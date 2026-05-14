import pandas as pd
from sqlalchemy.engine import Engine
from sqlalchemy.sql import text

from infrastructure.repository.attribute_options_repository import AttributeOptionsRepository
from infrastructure.repository.utils import short_disease_codes, short_disease_code, upper_short_disease_codes


_SQL_SELECT_THERAPY_TYPES = """
SELECT code, title
FROM trials_therapycomponentcategory;
"""

_SQL_SELECT_PRE_EXISTING_CONDITION_CATEGORIES = """
select code, title
from trials_preexistingconditioncategory;
"""

_SQL_SELECT_CYTOGENIC_MARKERS = """
SELECT m.code, m.title
FROM trials_marker m
JOIN trials_markercategoryconnection mcc ON m.id = mcc.marker_id
JOIN trials_markercategory mc ON mc.id = mcc.category_id
WHERE mc.code = 'cytogenic';
"""

_SQL_SELECT_MOLECULAR_MARKERS = """
SELECT m.code, m.title
FROM trials_marker m
JOIN trials_markercategoryconnection mcc ON m.id = mcc.marker_id
JOIN trials_markercategory mc ON mc.id = mcc.category_id
WHERE mc.code = 'molecular';
"""

_SQL_SELECT_THERAPY_COMPONENTS_BY_DISEASE_CODES = """
SELECT distinct tc.id, tc.title, tc.code
FROM trials_diseaseroundtherapyconnection drtc
JOIN trials_disease d ON drtc.disease_id = d.id
JOIN trials_therapy t ON drtc.therapy_id = t.id
JOIN trials_therapycomponentconnection tcc ON t.id = tcc.therapy_id
JOIN trials_therapycomponent tc ON tc.id = tcc.component_id
WHERE d.code IN :disease_codes
ORDER BY id;
"""

_SQL_SELECT_THERAPIES_BY_DISEASE_CODES = """
SELECT distinct t.id, t.code, t.title
FROM trials_diseaseroundtherapyconnection drtc
JOIN trials_disease d ON drtc.disease_id = d.id
JOIN trials_therapy t ON drtc.therapy_id = t.id
WHERE d.code IN :disease_codes
"""


class AttributeOptionsRepositoryImplementation(AttributeOptionsRepository):
    def __init__(self, engine: Engine):
        self._engine = engine

    def get_therapy_components_by_disease_codes(self, disease_codes: tuple[str, ...]) -> pd.DataFrame:
        query = text(_SQL_SELECT_THERAPY_COMPONENTS_BY_DISEASE_CODES)
        return pd.read_sql(query, self._engine, params={"disease_codes": upper_short_disease_codes(disease_codes)})

    def get_therapies_by_disease_codes(self, disease_codes: tuple[str, ...]) -> pd.DataFrame:
        query = text(_SQL_SELECT_THERAPIES_BY_DISEASE_CODES)
        return pd.read_sql(query, self._engine, params={"disease_codes": upper_short_disease_codes(disease_codes)})

    def get_therapy_types(self) -> pd.DataFrame:
        return pd.read_sql(_SQL_SELECT_THERAPY_TYPES, self._engine)

    def get_pre_existing_condition_categories(self) -> pd.DataFrame:
        return pd.read_sql(_SQL_SELECT_PRE_EXISTING_CONDITION_CATEGORIES, self._engine)

    def get_cytogenic_markers(self) -> pd.DataFrame:
        return pd.read_sql(_SQL_SELECT_CYTOGENIC_MARKERS, self._engine)

    def get_molecular_markers(self) -> pd.DataFrame:
        return pd.read_sql(_SQL_SELECT_MOLECULAR_MARKERS, self._engine)

    def get_brca1_mutations(self) -> pd.DataFrame:
        codes = {
            "c.68_69delAG", "c.5266dupC", "c.4035delAAGA", "c.181T>G", "c.5096G>A", "c.3700_3704delGTAAA",
            "c.68_69delAG",
            "c.5266dupC", "c.4035delAAGA", "c.181T>G", "c.5096G>A", "c.3700_3704delGTAAA", "c.68_69delAG", "c.5266dupC",
            "c.4035delAAGA", "c.181T>G", "c.5096G>A", "c.3700_3704delGTAAA", "c.68_69delAG", "c.5266dupC",
            "c.4035delAAGA",
            "c.181T>G", "c.5096G>A", "c.3700_3704delGTAAA", "c.68_69delAG", "c.5266dupC", "c.4035delAAGA", "c.181T>G",
            "c.5096G>A", "c.3700_3704delGTAAA", "c.68_69delAG", "c.5266dupC", "c.4035delAAGA", "c.181T>G", "c.5096G>A",
            "c.3700_3704delGTAAA", "c.68_69delAG", "c.5266dupC", "c.4035delAAGA", "c.181T>G", "c.5096G>A",
            "c.3700_3704delGTAAA", "c.68_69delAG", "c.5266dupC", "c.4035delAAGA", "c.181T>G", "c.5096G>A",
            "c.3700_3704delGTAAA", "c.68_69delAG", "c.5266dupC"}
        return self._mutation_codes_to_df(codes)

    def get_brca2_mutations(self) -> pd.DataFrame:
        codes = {"c.5946delT", "c.6174delT", "c.7008-1G>A", "c.7558C>T", "c.7617+1G>A", "c.7913_7917delTTAAA",
                 "c.7975A>T", "c.8168A>G", "c.8488-1G>A", "c.8537_8538delAG", "c.8572C>T", "c.8755delG",
                 "c.9097_9098insA", "c.9117G>A", "c.9154C>T", "c.9235delG", "c.9265+1G>A", "c.9308G>A", "c.9382C>T",
                 "c.9501+1G>A", "c.9610C>T", "c.9631delC", "c.9653delA", "c.9700C>T", "c.9816delC", "c.9852delT",
                 "c.9976A>T", "c.10095delC", "c.10150C>T", "c.10204C>T", "c.10230_10233delAGAA", "c.10247A>G",
                 "c.10276C>T", "c.10323C>T", "c.10350C>A", "c.10370A>G", "c.10411C>T", "c.10453C>T", "c.10509C>A",
                 "c.10580G>A", "c.10606C>T", "c.10632_10633delAG", "c.10647delC", "c.10692_10693insA", "c.10740C>T",
                 "c.10776_10777delAG", "c.10810C>T", "c.10824_10825delCT", "c.10830_10831delAA", "c.10844C>T"}
        return self._mutation_codes_to_df(codes)

    def get_pik3ca_mutations(self) -> pd.DataFrame:
        codes = {"c.3140A>G (p.H1047R)", "c.1624G>A (p.E542K)", "c.1633G>A (p.E545K)", "c.3140A>T (p.H1047L)",
                 "c.3140A>C (p.H1047P)", "c.1633G>C (p.E545Q)", "c.1625A>G (p.E542G)", "c.3143A>G (p.H1048R)",
                 "c.3145G>C (p.G1049R)", "c.1637A>G (p.Q546R)", "c.1637A>C (p.Q546P)", "c.1637A>T (p.Q546K)",
                 "c.3142C>T (p.H1048Y)", "c.3144T>G (p.H1048Q)", "c.3145G>A (p.G1049S)", "c.3146G>C (p.G1049A)",
                 "c.3146G>T (p.G1049V)", "c.3147G>A (p.G1049D)", "c.3147G>C (p.G1049E)", "c.3147G>T (p.G1049F)",
                 "c.3148G>A (p.G1049N)", "c.3148G>C (p.G1049T)", "c.3148G>T (p.G1049Y)", "c.3149G>A (p.G1049C)",
                 "c.3149G>C (p.G1049W)", "c.3149G>T (p.G1049H)", "c.3150G>A (p.G1049L)", "c.3150G>C (p.G1049M)",
                 "c.3150G>T (p.G1049I)", "c.3151G>A (p.G1049K)", "c.3151G>C (p.G1049R)", "c.3151G>T (p.G1049S)",
                 "c.3152G>A (p.G1049T)", "c.3152G>C (p.G1049V)", "c.3152G>T (p.G1049Y)", "c.3153G>A (p.G1049D)",
                 "c.3153G>C (p.G1049E)", "c.3153G>T (p.G1049F)", "c.3154G>A (p.G1049N)", "c.3154G>C (p.G1049T)",
                 "c.3154G>T (p.G1049Y)", "c.3155G>A (p.G1049C)", "c.3155G>C (p.G1049W)", "c.3155G>T (p.G1049H)",
                 "c.3156G>A (p.G1049L)", "c.3156G>C (p.G1049M)", "c.3156G>T (p.G1049I)", "c.3157G>A (p.G1049K)",
                 "c.3157G>C (p.G1049R)", "c.3157G>T (p.G1049S)"}
        return self._mutation_codes_to_df(codes)

    def get_tp53_mutations(self) -> pd.DataFrame:
        codes = {"R175H", "R248Q", "R248W", "R273C", "R273H", "R282W", "Y220C", "G245S", "R249S", "V157F", "R158L",
                 "G245D", "R196*", "H179R", "R213*", "R273L", "C242F", "R280K", "Y163C", "P278L", "H193R", "Y234C",
                 "C135Y", "D281G", "R306*", "V143A", "Q167K", "R110L", "G266V", "M133T", "G244D", "I195T", "R213Q",
                 "G245V", "H179Y", "D281H", "A138V", "L194F", "G154V", "Y163N", "R158H", "R342*", "R196Q", "Q136*",
                 "P151S", "H193Y", "A159V", "L111Q", "E285K", "R213L"}
        return self._mutation_codes_to_df(codes)

    def get_esr1_mutations(self) -> pd.DataFrame:
        codes = {"c.743G>A (p.R248Q)", "c.818G>A (p.R273H)", "c.524G>A (p.R175H)", "c.844C>T (p.R282W)",
                 "c.742C>T (p.R248W)", "c.817C>T (p.R273C)", "c.743G>C (p.R248P)", "c.818G>C (p.R273P)",
                 "c.844C>G (p.R282G)", "c.524G>C (p.R175P)", "c.743G>T (p.R248L)", "c.818G>T (p.R273L)",
                 "c.844C>A (p.R282Q)", "c.524G>T (p.R175L)", "c.743G>A (p.R248Q)", "c.818G>A (p.R273H)",
                 "c.524G>A (p.R175H)", "c.844C>T (p.R282W)", "c.742C>T (p.R248W)", "c.817C>T (p.R273C)",
                 "c.743G>C (p.R248P)", "c.818G>C (p.R273P)", "c.844C>G (p.R282G)", "c.524G>C (p.R175P)",
                 "c.743G>T (p.R248L)", "c.818G>T (p.R273L)", "c.844C>A (p.R282Q)", "c.524G>T (p.R175L)",
                 "c.743G>A (p.R248Q)", "c.818G>A (p.R273H)", "c.524G>A (p.R175H)", "c.844C>T (p.R282W)",
                 "c.742C>T (p.R248W)", "c.817C>T (p.R273C)", "c.743G>C (p.R248P)", "c.818G>C (p.R273P)",
                 "c.844C>G (p.R282G)", "c.524G>C (p.R175P)", "c.743G>T (p.R248L)", "c.818G>T (p.R273L)",
                 "c.844C>A (p.R282Q)", "c.524G>T (p.R175L)", "c.743G>A (p.R248Q)", "c.818G>A (p.R273H)",
                 "c.524G>A (p.R175H)", "c.844C>T (p.R282W)", "c.742C>T (p.R248W)", "c.817C>T (p.R273C)",
                 "c.743G>C (p.R248P)", "c.818G>C (p.R273P)"}
        return self._mutation_codes_to_df(codes)

    def get_brca1_interpretations(self) -> pd.DataFrame:
        return self._get_common_mutation_interpretations()

    def get_brca2_interpretations(self) -> pd.DataFrame:
        return self._get_common_mutation_interpretations()

    def get_pik3ca_interpretations(self) -> pd.DataFrame:
        return self._get_common_mutation_interpretations()

    def get_tp53_interpretations(self) -> pd.DataFrame:
        return self._get_common_mutation_interpretations()

    def get_esr1_interpretations(self) -> pd.DataFrame:
        return self._get_common_mutation_interpretations()

    def _mutation_codes_to_df(self, codes: set[str]) -> pd.DataFrame:
        items = []
        for code in codes:
            items.append({"code": code, "title": code, "trial_substrings": [code]})
        df = pd.DataFrame(items)
        return df

    def _get_common_mutation_interpretations(self) -> pd.DataFrame:
        items = [
            {"code": "likely_pathogenic", "title": "Likely pathogenic"},
            {"code": "variant_of_uncertain_significance", "title": "Variant of Uncertain Significance (VUS)"},
            {"code": "likely_benign", "title": "Likely benign"},
            {"code": "benign", "title": "Benign"},
            {"code": "no_mutation_detected", "title": "No mutation detected"},
        ]
        return pd.DataFrame(items)

    def get_estrogen_receptor_status_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_estrogenreceptorstatus;""")
        return pd.read_sql(query, self._engine)

    def get_progesterone_receptor_status_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_progesteronereceptorstatus;""")
        return pd.read_sql(query, self._engine)

    def get_her2_status_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_her2status;""")
        return pd.read_sql(query, self._engine)

    def get_histologic_type_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_histologictype;""")
        return pd.read_sql(query, self._engine)

    def get_hrd_status_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_hrdstatus;""")
        return pd.read_sql(query, self._engine)

    def get_hr_status_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_hrstatus;""")
        return pd.read_sql(query, self._engine)

    def get_mutation_gene_options(self) -> pd.DataFrame:
        query = text("""SELECT DISTINCT code, title FROM trials_mutationgene ORDER BY code;""")
        return pd.read_sql(query, self._engine)

    def get_mutation_variant_options(self) -> pd.DataFrame:
        query = text("""SELECT DISTINCT code, title FROM trials_mutationcode ORDER BY code;""")
        return pd.read_sql(query, self._engine)

    def get_mutation_interpretation_options(self) -> pd.DataFrame:
        query = text("""
select
    mg.code || '__' || mi.code as code,
    mg.title || ' ' || mi.title as title
from trials_mutationgene mg
join trials_mutationinterpretation mi
on true;
        """)
        return pd.read_sql(query, self._engine)

    def get_mutation_origin_options(self) -> pd.DataFrame:
        query = text("""
select
    mo.code || '__' || gene_or_code.code as code,
    mo.title || ' ' || gene_or_code.title as title
from trials_mutationorigin mo
join (
    select mg.code, mg.title
        from trials_mutationgene mg
        where mg.code in ('brca1', 'brca2', 'tp53')
    union
    select mc.code, mc.title
        from trials_mutationcode mc
        join trials_mutationgene mg on mc.gene_id = mg.id
        where mg.code in ('brca1', 'brca2', 'tp53')
) as gene_or_code
on true;
""")
        return pd.read_sql(query, self._engine)

    def get_trial_type_options(self, disease_code: str) -> pd.DataFrame:
        query = text(f"""
select tt.id, tt.code, tt.title, tt.llm_hint from trials_trialtype tt
join trials_trialtypediseaseconnection ttdc on tt.id = ttdc.trial_type_id
join trials_disease d on ttdc.disease_id = d.id
where d.code = '{disease_code}';
""")
        return pd.read_sql(query, self._engine)

    def get_tumor_stage_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_tumorstage;""")
        return pd.read_sql(query, self._engine)

    def get_node_stage_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_nodesstage;""")
        return pd.read_sql(query, self._engine)

    def get_metastasis_stage_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_distantmetastasisstage;""")
        return pd.read_sql(query, self._engine)

    def get_modality_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_stagingmodality;""")
        return pd.read_sql(query, self._engine)

    def get_language_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_language;""")
        return pd.read_sql(query, self._engine)

    def get_language_skill_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_languageskilllevel;""")
        return pd.read_sql(query, self._engine)

    def get_toxicity_grade_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_toxicitygrade;""")
        return pd.read_sql(query, self._engine)

    def get_planned_therapy_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_plannedtherapy;""")
        return pd.read_sql(query, self._engine)

    def get_language_skill_product_options(self) -> pd.DataFrame:
        query = text("""select
        lsl.code || '__' || l.code as code,
        lsl.title || ' ' || l.title as title
        from trials_language l
        join trials_languageskilllevel lsl on true;
        ;""")
        return pd.read_sql(query, self._engine)

    def get_binet_stage_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_binetstage;""")
        return pd.read_sql(query, self._engine)

    def get_protein_expression_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_proteinexpression;""")
        return pd.read_sql(query, self._engine)

    def get_richter_transformation_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_richtertransformation;""")
        return pd.read_sql(query, self._engine)

    def get_tumor_burden_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_tumorburden;""")
        return pd.read_sql(query, self._engine)

    def get_trial_purpose_options(self) -> pd.DataFrame:
        query = text("""SELECT id, code, title FROM trials_trialpurpose;""")
        return pd.read_sql(query, self._engine)
