import pytest

from app.organizations import Organization, OrganizationRegistry, UnknownOrganization


@pytest.fixture
def registry() -> OrganizationRegistry:
    return OrganizationRegistry(
        [
            Organization(alias="alpha", title="Alpha Health", endpoint_url="https://a/fhir"),
            Organization(alias="beta", title="Beta Clinic", endpoint_url="https://b/fhir"),
        ]
    )


def test_get_known_alias_returns_org(registry):
    org = registry.get("alpha")
    assert org.title == "Alpha Health"
    assert org.endpoint_url == "https://a/fhir"


def test_get_unknown_alias_raises(registry):
    with pytest.raises(UnknownOrganization):
        registry.get("missing")


def test_list_returns_all_orgs(registry):
    aliases = {o.alias for o in registry.list()}
    assert aliases == {"alpha", "beta"}


def test_empty_registry_lists_nothing():
    assert OrganizationRegistry([]).list() == []
