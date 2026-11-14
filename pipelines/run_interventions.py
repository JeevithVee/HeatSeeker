"""Job: city planting records -> bronze -> silver.interventions.

    python -m pipelines.run_interventions nyc [--raw PATH]

Runs as a Databricks job or locally; see pipelines/io.py for where tables go.
"""
import argparse

from ingest.us import nyc_tree_points
from pipelines import interventions, io

ADAPTERS = {
    "nyc": nyc_tree_points,
}


def run(city_id, raw_path=None):
    adapter = ADAPTERS[city_id]
    raw_path = raw_path or adapter.fetch(io.LOCAL_ROOT / "bronze" / adapter.SOURCE_ID)
    raw = adapter.read_raw(raw_path)

    bronze = adapter.to_bronze(raw)
    print("bronze ->", io.write_table(bronze, f"bronze.{adapter.SOURCE_ID}"))

    records = adapter.to_records(bronze)
    print(interventions.cleaning_report(records).to_string(index=False))

    silver = interventions.build_interventions(records)
    print("silver ->", io.write_table(silver, "silver.interventions", city_id=city_id))
    print(f"{len(silver)} cell-years, {silver['site_id'].nunique()} cells, "
          f"{silver['trees_planted'].sum()} dated plantings")
    return silver


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("city_id", choices=sorted(ADAPTERS))
    parser.add_argument("--raw", help="already-downloaded source file")
    args = parser.parse_args()
    run(args.city_id, args.raw)
