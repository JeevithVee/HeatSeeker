"""Load site effects with the Databricks CLI and a SQL warehouse (stdlib only).

Validate before upload and replace one city's rows in a single Delta transaction.
"""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


SQL_TYPES = {
    "country_code": "STRING", "city_id": "STRING", "site_id": "STRING", "variant": "STRING",
    "treatment_year": "INT", "intervention_type": "STRING", "dose_trees": "INT",
    "n_pre_scenes": "INT", "n_post_scenes": "INT", "n_controls": "INT",
    "effect_k": "DOUBLE", "effect_se_k": "DOUBLE", "ci_low_k": "DOUBLE", "ci_high_k": "DOUBLE",
    "placebo_p": "DOUBLE", "mde_k": "DOUBLE", "quality_label": "STRING", "event_study_json": "STRING",
    "panel_version": "STRING", "method_version": "STRING", "evaluated_at_utc": "TIMESTAMP",
}


def identifier(value):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Invalid SQL identifier: {value!r}")
    return value


def validate_csv(path, city):
    keys = set()
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != list(SQL_TYPES):
            raise ValueError("CSV columns must match gold.site_effects in order")
        for line, row in enumerate(reader, start=2):
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f"Malformed CSV row at line {line}")
            if row["city_id"] != city:
                raise ValueError(f"Line {line}: expected city_id={city!r}, got {row['city_id']!r}")
            key = (row["site_id"], row["variant"])
            if not key[0] or key in keys:
                raise ValueError(f"Line {line}: empty or duplicate site/variant {key}")
            if row["variant"] not in ("all", "excl_batch_dated"):
                raise ValueError(f"Line {line}: invalid variant")
            if row["quality_label"] not in ("detected", "not_detectable", "inconclusive"):
                raise ValueError(f"Line {line}: invalid quality_label")
            if row["event_study_json"]:
                event = json.loads(row["event_study_json"])
                if not isinstance(event, dict):
                    raise ValueError(f"Line {line}: event_study_json must be an object")
                for year, effect in event.items():
                    int(year)
                    float(effect)
            keys.add(key)
    if not keys:
        raise ValueError("Refusing to replace city rows with an empty CSV")
    return len(keys)


class Warehouse:
    def __init__(self, profile, warehouse_id=None):
        self.cli = shutil.which("databricks") or str(Path.home() / ".local/bin/databricks")
        self.profile = profile
        self.warehouse_id = warehouse_id

    def command(self, *args, json_output=False):
        cmd = [self.cli, *args, "-p", self.profile]
        if json_output:
            cmd += ["-o", "json"]
        result = subprocess.run(cmd, check=True, text=True, capture_output=True)
        if not json_output:
            return result.stdout
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Databricks returned non-JSON output despite -o json") from exc

    def sql(self, statement):
        if not self.warehouse_id:
            warehouses = self.command("warehouses", "list", json_output=True)
            candidates = [w for w in warehouses if w.get("enable_serverless_compute")]
            if not candidates:
                raise RuntimeError("No serverless SQL warehouse; set DATABRICKS_WAREHOUSE_ID")
            candidates.sort(key=lambda w: w.get("state") != "RUNNING")
            self.warehouse_id = candidates[0]["id"]
        data = self.command("api", "post", "/api/2.0/sql/statements", "--json", json.dumps({
            "warehouse_id": self.warehouse_id, "statement": statement,
            "wait_timeout": "50s", "on_wait_timeout": "CONTINUE",
        }), json_output=True)
        deadline = time.monotonic() + 900
        while data["status"]["state"] in ("PENDING", "RUNNING"):
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Statement {data['statement_id']} still running; inspect before retrying")
            print(f"[load_gold] SQL {data['status']['state']} ({data['statement_id']})", flush=True)
            time.sleep(2)
            data = self.command("api", "get", f"/api/2.0/sql/statements/{data['statement_id']}", json_output=True)
        if data["status"]["state"] != "SUCCEEDED":
            raise RuntimeError(f"SQL failed: {json.dumps(data['status'])}")
        if data.get("manifest", {}).get("truncated"):
            raise RuntimeError("SQL verification response was truncated")
        return data.get("result", {}).get("data_array", [])


def source_sql(dest):
    # pandas/csv double embedded quotes; Spark's default escape is a backslash.
    return (f"read_files('{dest}', format => 'csv', header => true, inferSchema => false, "
            "escape => '\"', mode => 'FAILFAST')")


def load(warehouse, path, city, catalog):
    identifier(city)
    identifier(catalog)
    expected = validate_csv(path, city)
    table = f"{catalog}.gold.site_effects"
    volume = f"/Volumes/{catalog}/gold/files/site_effects"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    dest = f"{volume}/{city}_{digest}.csv"
    print(f"[load_gold] uploading {expected:,} validated rows to {dest}", flush=True)
    warehouse.command("fs", "mkdir", f"dbfs:{volume}")
    warehouse.command("fs", "cp", str(path), f"dbfs:{dest}", "--overwrite")
    source = source_sql(dest)
    rows = warehouse.sql(f"SELECT COUNT(*), COUNT_IF(city_id IS NULL OR city_id <> '{city}'), "
                         "COUNT_IF(event_study_json IS NOT NULL AND "
                         "from_json(event_study_json, 'MAP<STRING, DOUBLE>') IS NULL) "
                         f"FROM {source}")
    if len(rows) != 1 or [int(n) for n in rows[0]] != [expected, 0, 0]:
        raise RuntimeError(f"Uploaded CSV failed SQL validation: {rows}")
    schema = ", ".join(f"{name} {kind}" for name, kind in SQL_TYPES.items())
    warehouse.sql(f"CREATE TABLE IF NOT EXISTS {table} ({schema}) USING DELTA COMMENT "
                  "'Measured surface-temperature differences, Kelvin; negative = cooling. "
                  "Surface temperature is not felt temperature.'")
    description = warehouse.sql(f"DESCRIBE TABLE {table}")
    actual = {row[0]: row[1].upper() for row in description if row[0] in SQL_TYPES}
    if actual != SQL_TYPES:
        raise RuntimeError(f"Target table schema differs from gold.site_effects: {actual}")
    # Follow the existing table order; column-list REPLACE WHERE needs newer runtimes.
    select = ", ".join(f"CAST({row[0]} AS {SQL_TYPES[row[0]]})"
                       for row in description if row[0] in SQL_TYPES)
    print(f"[load_gold] atomically replacing {city} in {table}", flush=True)
    warehouse.sql(f"INSERT INTO {table} REPLACE WHERE city_id = '{city}' SELECT {select} FROM {source}")
    counts = warehouse.sql(f"SELECT COUNT(*), COUNT(DISTINCT site_id, variant), "
                           "COUNT_IF(event_study_json IS NOT NULL AND "
                           "from_json(event_study_json, 'MAP<STRING, DOUBLE>') IS NULL) "
                           f"FROM {table} WHERE city_id = '{city}'")
    if len(counts) != 1 or [int(n) for n in counts[0]] != [expected, expected, 0]:
        raise RuntimeError(f"Loaded table failed verification: {counts}")
    parity = warehouse.sql(
        f"WITH incoming AS (SELECT {select} FROM {source}), "
        f"stored AS (SELECT * FROM {table} WHERE city_id = '{city}'), "
        "missing AS (SELECT * FROM incoming EXCEPT ALL SELECT * FROM stored), "
        "extra AS (SELECT * FROM stored EXCEPT ALL SELECT * FROM incoming) "
        "SELECT (SELECT COUNT(*) FROM missing), (SELECT COUNT(*) FROM extra)"
    )
    if len(parity) != 1 or [int(n) for n in parity[0]] != [0, 0]:
        raise RuntimeError(f"Loaded rows differ from the source CSV: {parity}")
    summary = warehouse.sql(f"SELECT variant, quality_label, COUNT(*) AS n FROM {table} "
                            f"WHERE city_id = '{city}' GROUP BY ALL ORDER BY ALL")
    print(json.dumps({"table": table, "city_id": city, "rows": expected,
                      "source_sha256": digest, "exact_csv_parity": True, "labels": summary}, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", type=Path)
    ap.add_argument("city")
    ap.add_argument("profile", nargs="?", default="heatseeker")
    ap.add_argument("catalog", nargs="?", default="heatseeker")
    args = ap.parse_args()
    warehouse = Warehouse(args.profile, os.environ.get("DATABRICKS_WAREHOUSE_ID"))
    try:
        load(warehouse, args.csv, args.city, args.catalog)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.stderr.strip() or exc.stdout.strip() or str(exc)) from exc


if __name__ == "__main__":
    main()
