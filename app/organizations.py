import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Organization:
    alias: str
    title: str
    endpoint_url: str


class UnknownOrganization(KeyError):
    pass


class OrganizationRegistry:
    def __init__(self, organizations: list[Organization]):
        self._by_alias: dict[str, Organization] = {o.alias: o for o in organizations}

    @classmethod
    def from_file(cls, path: str | Path) -> "OrganizationRegistry":
        data = json.loads(Path(path).read_text())
        orgs = [Organization(**item) for item in data["organizations"]]
        return cls(orgs)

    def get(self, alias: str) -> Organization:
        org = self._by_alias.get(alias)
        if org is None:
            raise UnknownOrganization(alias)
        return org

    def list(self) -> list[Organization]:
        return list(self._by_alias.values())
