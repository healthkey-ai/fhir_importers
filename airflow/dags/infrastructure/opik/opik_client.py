from opik import Opik


def create_opik_client() -> Opik:
    opik_client = Opik(project_name="cancerbot-airflow")
    return opik_client
