"""Local build of silver.panel, same logic as build_silver_panel.py (the Databricks job).

Interim delivery route while there is no Databricks workspace: reads the Earth
Engine CSVs and writes one Parquet file with the frozen silver.panel columns.

    python pipelines/panel/build_panel_local.py data/satellite/nyc pipelines/panel/out nyc
"""
import glob
import sys

import pandas as pd

MIN_VALID_PIXEL_FRAC = 0.8
SOURCE = "Landsat Collection 2 Level 2 ST_B10 via Google Earth Engine"
LICENSE = "USGS Landsat: public domain"

COLUMNS = [
    "country_code", "city_id", "site_id", "scene_id", "acquired_at_utc", "acquired_date", "year", "sensor",
    "lst_mean_k", "lst_median_k", "lst_std_k", "valid_pixel_count", "valid_pixel_frac", "is_clear",
    "scene_cloud_cover_frac", "city_clear_frac", "sun_elevation_deg", "wrs_path", "wrs_row",
    "tmax_c", "tmin_c", "wind_speed_ms", "precip_mm", "source", "license",
]


def build(in_dir, city_id):
    files = sorted(glob.glob(f"{in_dir}/{city_id}_lst_*.csv"))
    lst = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    lst = lst.drop_duplicates(["city_id", "site_id", "scene_id"])
    lst["acquired_at_utc"] = pd.to_datetime(lst["acquired_at_utc"], utc=True)
    lst["acquired_date"] = lst["acquired_at_utc"].dt.date
    lst["year"] = lst["acquired_at_utc"].dt.year.astype("int32")
    lst["valid_pixel_count"] = lst["valid_pixel_count"].astype("int32")
    lst["wrs_path"] = lst["wrs_path"].astype("int32")
    lst["wrs_row"] = lst["wrs_row"].astype("int32")
    lst["is_clear"] = lst["valid_pixel_frac"] >= MIN_VALID_PIXEL_FRAC

    n_cells = lst["site_id"].nunique()
    lst["city_clear_frac"] = lst.groupby("scene_id")["is_clear"].transform("sum") / n_cells

    w = pd.read_csv(f"{in_dir}/{city_id}_weather.csv")
    w["acquired_date"] = pd.to_datetime(w["date"]).dt.date
    w["tmax_c"] = w["tmax_k"] - 273.15
    w["tmin_c"] = w["tmin_k"] - 273.15
    lst = lst.merge(w[["acquired_date", "tmax_c", "tmin_c", "wind_speed_ms", "precip_mm"]], on="acquired_date", how="left")

    lst["source"] = SOURCE
    lst["license"] = LICENSE
    return lst[COLUMNS].sort_values(["scene_id", "site_id"]).reset_index(drop=True), files


def main():
    in_dir, out_dir, city_id = sys.argv[1:4]
    panel, files = build(in_dir, city_id)
    out = f"{out_dir}/{city_id}_silver_panel.parquet"
    panel.to_parquet(out, index=False, compression="zstd")
    scenes = panel.drop_duplicates("scene_id")
    print(f"{len(files)} input files -> {out}")
    print(f"rows {len(panel):,}  cells {panel.site_id.nunique():,}  scenes {len(scenes)}  "
          f"scenes with city_clear_frac>=0.5: {(scenes.city_clear_frac >= 0.5).sum()}")
    print(scenes.groupby(["year", "sensor"]).agg(scenes=("scene_id", "size"), usable=("city_clear_frac", lambda s: (s >= 0.5).sum())).to_string())
    print("missing weather rows:", int(panel.tmax_c.isna().sum()))


if __name__ == "__main__":
    main()
