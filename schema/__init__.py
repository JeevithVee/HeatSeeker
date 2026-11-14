"""Standard table definitions shared by all modules.

The YAML files in this directory are the source of truth. This module only
loads them and checks DataFrames against them.
"""
from pathlib import Path

import yaml

_DIR = Path(__file__).parent

_TABLES = yaml.safe_load((_DIR / "tables.yaml").read_text())
_ROLES = yaml.safe_load((_DIR / "roles.yaml").read_text())

SCHEMA_VERSION = _TABLES["version"]
H3_RESOLUTION = _TABLES["h3_resolution"]
CITY_IDS = tuple(_TABLES["city_ids"])
ROLES = tuple(_ROLES["roles"])
TABLES = _TABLES["tables"]


def columns(table):
    """Ordered column names for a standard table, e.g. 'silver.interventions'."""
    return list(TABLES[table]["columns"])


def validate(df, table):
    """Check a pandas DataFrame against a table definition.

    Raises ValueError listing every problem: missing or unexpected columns,
    and nulls in columns declared non-nullable. Returns the frame with its
    columns in schema order.
    """
    spec = TABLES[table]["columns"]
    problems = []
    missing = [c for c in spec if c not in df.columns]
    extra = [c for c in df.columns if c not in spec]
    if missing:
        problems.append(f"missing columns: {missing}")
    if extra:
        problems.append(f"unexpected columns: {extra}")
    for name, col in spec.items():
        if name in df.columns and not col.get("nullable", True) and df[name].isna().any():
            problems.append(f"nulls in non-nullable column {name}")
    if "role" in df.columns and "role" in spec:
        bad = sorted(set(df["role"].dropna()) - set(ROLES))
        if bad:
            problems.append(f"unknown roles: {bad}")
    if problems:
        raise ValueError(f"{table}: " + "; ".join(problems))
    return df[list(spec)]
