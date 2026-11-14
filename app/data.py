"""Data access for the app.

On Databricks this module is the one place that switches to SQL against the
gold/silver Unity Catalog tables (via databricks.sql or spark). Everywhere
else - and whenever a live query fails - it reads the precomputed parquet
snapshots, so the app always has something to show (shared brief: fall back
to precomputed gold tables).

Set HEATSEEKER_DATA_DIR to point at the snapshot directory; default is demo/data.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import yaml

REPO = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("HEATSEEKER_DATA_DIR", REPO / "demo" / "data"))

TABLES = {
    "features": "silver_features.parquet",
    "interventions": "silver_interventions.parquet",
    "site_effects": "gold_site_effects.parquet",
    "recommendations": "gold_recommendations.parquet",
    "panel_sample": "panel_sample.parquet",
    "prediction_log": "prediction_log.parquet",
    "prediction_scores": "prediction_scores.parquet",
}

# Where the app logs plantings entered in the Track view.
NEW_PLANTINGS_PATH = DATA_DIR / "new_plantings.parquet"


def load_config() -> dict:
    return yaml.safe_load((REPO / "config" / "us" / "config.yaml").read_text())


def load_table(name: str) -> pd.DataFrame:
    """Load a standard table; empty frame if the snapshot is missing."""
    path = DATA_DIR / TABLES[name]
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def log_planting(entry: dict) -> pd.DataFrame:
    """Append one planting logged in the app (the 'Plant' step of the loop).

    On Databricks this becomes an INSERT into silver.interventions' staging
    table; locally it appends to a parquet file next to the snapshots.
    """
    row = pd.DataFrame([entry])
    if NEW_PLANTINGS_PATH.exists():
        row = pd.concat([pd.read_parquet(NEW_PLANTINGS_PATH), row], ignore_index=True)
    row.to_parquet(NEW_PLANTINGS_PATH, index=False)
    return row


def load_new_plantings() -> pd.DataFrame:
    if NEW_PLANTINGS_PATH.exists():
        return pd.read_parquet(NEW_PLANTINGS_PATH)
    return pd.DataFrame()
