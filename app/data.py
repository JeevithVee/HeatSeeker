"""Data access for the app: live Unity Catalog tables with snapshot fallback.

Mode 1 - live: when DATABRICKS_WAREHOUSE_HTTP_PATH is set (app.yaml) and
credentials exist (a Databricks App injects DATABRICKS_HOST / CLIENT_ID /
CLIENT_SECRET for its service principal), each table is read from
heatseeker.* through the SQL warehouse.

Mode 2 - snapshot: everywhere else, and WHENEVER a live query fails (no
grants yet, warehouse down, table missing), the precomputed parquet
snapshot under HEATSEEKER_DATA_DIR serves instead - the brief's sanctioned
fallback. The app keeps working either way; `source()` reports which mode
each table came from.
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

# Unity Catalog sources for live mode. panel_sample and prediction_scores
# are derived files, snapshot-only.
LIVE_TABLES = {
    "features": "heatseeker.silver.features",
    "interventions": "heatseeker.silver.interventions",
    "site_effects": "heatseeker.gold.site_effects",
    "recommendations": "heatseeker.gold.recommendations",
    "prediction_log": "heatseeker.gold.prediction_log",
}

PLANTING_TABLE = "heatseeker.gold.app_planting_log"
NEW_PLANTINGS_PATH = DATA_DIR / "new_plantings.parquet"

_sources: dict[str, str] = {}
_conn = None


def source(name: str | None = None):
    """'live' or 'snapshot' per table; overall summary when name is None."""
    if name:
        return _sources.get(name, "snapshot")
    vals = set(_sources.values())
    return "live" if vals == {"live"} else ("mixed" if "live" in vals else "snapshot")


def _live_ready() -> bool:
    return bool(os.environ.get("DATABRICKS_WAREHOUSE_HTTP_PATH")
                and os.environ.get("DATABRICKS_HOST")
                and os.environ.get("DATABRICKS_CLIENT_ID"))


def _connect():
    global _conn
    if _conn is not None:
        return _conn
    from databricks import sql as dbsql
    from databricks.sdk.core import Config, oauth_service_principal

    host = os.environ["DATABRICKS_HOST"]
    cfg = Config(host=f"https://{host}" if not host.startswith("http") else host,
                 client_id=os.environ["DATABRICKS_CLIENT_ID"],
                 client_secret=os.environ["DATABRICKS_CLIENT_SECRET"])
    _conn = dbsql.connect(
        server_hostname=cfg.host.replace("https://", ""),
        http_path=os.environ["DATABRICKS_WAREHOUSE_HTTP_PATH"],
        credentials_provider=lambda: oauth_service_principal(cfg),
    )
    return _conn


def _live_query(query: str, params: dict | None = None) -> pd.DataFrame:
    global _conn
    try:
        with _connect().cursor() as c:
            c.execute(query, params)
            return c.fetchall_arrow().to_pandas()
    except Exception:
        _conn = None  # stale connection: rebuild once on the next call
        raise


def load_config() -> dict:
    return yaml.safe_load((REPO / "config" / "us" / "config.yaml").read_text())


def load_table(name: str) -> pd.DataFrame:
    if name in LIVE_TABLES and _live_ready():
        try:
            df = _live_query(f"SELECT * FROM {LIVE_TABLES[name]}")
            _sources[name] = "live"
            return df
        except Exception:
            pass  # fall through to snapshot
    _sources[name] = "snapshot"
    path = DATA_DIR / TABLES[name]
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def log_planting(entry: dict) -> str:
    """Record one planting (the 'Plant' step). Returns where it landed.

    Live mode inserts into the app's own staging table (never Agent 1's
    silver.interventions); otherwise appends to a local parquet file.
    """
    if _live_ready():
        try:
            _live_query(
                f"""INSERT INTO {PLANTING_TABLE}
                (country_code, city_id, site_id, intervention_type,
                 trees_planted, planted_date, cost_usd, logged_by,
                 logged_at_utc)
                VALUES (:country_code, :city_id, :site_id,
                 :intervention_type, :trees_planted,
                 CAST(:planted_date AS DATE), :cost_usd, :logged_by,
                 CAST(:logged_at_utc AS TIMESTAMP))""",
                entry)
            return PLANTING_TABLE
        except Exception:
            pass
    row = pd.DataFrame([entry])
    if NEW_PLANTINGS_PATH.exists():
        row = pd.concat([pd.read_parquet(NEW_PLANTINGS_PATH), row],
                        ignore_index=True)
    NEW_PLANTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    row.to_parquet(NEW_PLANTINGS_PATH, index=False)
    return str(NEW_PLANTINGS_PATH.name)


def load_new_plantings() -> pd.DataFrame:
    if _live_ready():
        try:
            return _live_query(
                f"SELECT * FROM {PLANTING_TABLE} ORDER BY logged_at_utc DESC")
        except Exception:
            pass
    if NEW_PLANTINGS_PATH.exists():
        return pd.read_parquet(NEW_PLANTINGS_PATH)
    return pd.DataFrame()
