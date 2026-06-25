import click

from .admin import token, whoami
from .fhir import fhir
from .patient import connect, patient
from .test_patient import test_patient


@click.group(help="HealthEx admin / testing CLI. Reads creds from .env.")
@click.version_option("0.1")
def main() -> None:
    pass


main.add_command(connect)
main.add_command(patient)
main.add_command(fhir)
main.add_command(test_patient)
main.add_command(whoami)
main.add_command(token)


if __name__ == "__main__":
    main()
