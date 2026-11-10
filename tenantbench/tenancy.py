"""Tenant layout for the five BIRD dev databases (Hasil_ValidatorTenant_0).

Each database has one root table whose rows are split into 4 tenants by a fixed hash.
Every other tenant table inherits its tenant through one declared foreign key to a table
listed before it. Tables not listed are shared reference tables and get no RLS.
Names are the lowercased BIRD names, which is how they are created in PostgreSQL.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

N_TENANTS = 4
SALT = "tenantbench-2026:"


def tenant_of(key) -> int:
    h = hashlib.sha256((SALT + str(key)).encode("utf-8")).hexdigest()
    return 1 + int(h[:8], 16) % N_TENANTS


@dataclass(frozen=True)
class Root:
    table: str
    key: str  # column whose value is hashed


@dataclass(frozen=True)
class Child:
    table: str
    column: str  # FK column in this table
    parent: str
    parent_column: str


@dataclass(frozen=True)
class Layout:
    db: str
    root: Root
    children: tuple[Child, ...]

    @property
    def tenant_tables(self) -> frozenset[str]:
        return frozenset({self.root.table, *(c.table for c in self.children)})


LAYOUTS = {
    "financial": Layout("financial", Root("district", "district_id"), (
        Child("account", "district_id", "district", "district_id"),
        Child("client", "district_id", "district", "district_id"),
        Child("disp", "account_id", "account", "account_id"),
        Child("loan", "account_id", "account", "account_id"),
        Child("order", "account_id", "account", "account_id"),
        Child("trans", "account_id", "account", "account_id"),
        Child("card", "disp_id", "disp", "disp_id"),
    )),
    "formula_1": Layout("formula_1", Root("seasons", "year"), (
        Child("races", "year", "seasons", "year"),
        Child("results", "raceid", "races", "raceid"),
        Child("laptimes", "raceid", "races", "raceid"),
        Child("pitstops", "raceid", "races", "raceid"),
        Child("qualifying", "raceid", "races", "raceid"),
        Child("driverstandings", "raceid", "races", "raceid"),
        Child("constructorstandings", "raceid", "races", "raceid"),
        Child("constructorresults", "raceid", "races", "raceid"),
    )),
    "superhero": Layout("superhero", Root("publisher", "id"), (
        Child("superhero", "publisher_id", "publisher", "id"),
        Child("hero_power", "hero_id", "superhero", "id"),
        Child("hero_attribute", "hero_id", "superhero", "id"),
    )),
    "toxicology": Layout("toxicology", Root("molecule", "molecule_id"), (
        Child("atom", "molecule_id", "molecule", "molecule_id"),
        Child("bond", "molecule_id", "molecule", "molecule_id"),
        Child("connected", "atom_id", "atom", "atom_id"),
    )),
    # Root key is County, not CDSCode, so one county is never split across tenants.
    "california_schools": Layout("california_schools", Root("schools", "county"), (
        Child("frpm", "cdscode", "schools", "cdscode"),
        Child("satscores", "cds", "schools", "cdscode"),
    )),
}


def schema_name(db: str) -> str:
    return f"bird_{db}"
