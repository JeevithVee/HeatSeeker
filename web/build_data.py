"""Build the static data files the website reads.

Nothing is estimated here. Every number is copied or aggregated from the
standard tables:

    silver.features, silver.interventions            (Agent 1)
    silver.panel                                     (Agent 2)
    gold.site_effects                                (Agent 3)
    gold.recommendations, panel series per site      (Agent 4)

Storage units are kept (Kelvin, metres, fractions 0-1). The browser converts
to display units from the config that is copied into meta.json.

    python web/build_data.py --snapshot demo/data_real --panel-dir data/panel
"""
import argparse
import json
from pathlib import Path

import h3
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "static" / "data"

# Scenes that cover most of the city, recent Landsat 8/9 summers only.
HEAT_MIN_CITY_CLEAR = 0.5
HEAT_FROM_YEAR = 2022
HEAT_SENSORS = ("LANDSAT_8", "LANDSAT_9")
TREATMENT_WINDOW = (2015, 2019)


def r(value, digits):
    """Round, turning missing values into None so JSON stays valid."""
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def heat_by_cell(panel):
    """Mean summer surface temperature of each cell relative to the city
    median of the same scene, in Kelvin. Positive means hotter than the city."""
    p = panel[(panel["city_clear_frac"] >= HEAT_MIN_CITY_CLEAR) & panel["is_clear"]
              & panel["sensor"].isin(HEAT_SENSORS) & (panel["year"] >= HEAT_FROM_YEAR)]
    rel = p["lst_median_k"] - p.groupby("scene_id")["lst_median_k"].transform("median")
    g = rel.groupby(p["site_id"]).agg(["mean", "size"])
    return g["mean"], g["size"], p["scene_id"].nunique()


def build_city(city, feats, ints, effects, recs, series, panel):
    f = feats[feats["city_id"] == city].set_index("site_id")
    iv = ints[ints["city_id"] == city]
    planted_all = iv.groupby("site_id")["trees_planted"].sum()
    in_window = iv[iv["plant_year"].between(*TREATMENT_WINDOW)]
    planted_window = in_window.groupby("site_id")["trees_planted"].sum()
    by_year = {sid: dict(zip(g["plant_year"].astype(int), g["trees_planted"].astype(int)))
               for sid, g in iv.groupby("site_id")}

    e = effects[(effects["city_id"] == city) & (effects["variant"] == "all")].set_index("site_id")
    rc = recs[recs["city_id"] == city].set_index("site_id")
    heat, heat_n, heat_scenes = heat_by_cell(panel)

    features = []
    for sid, row in f.iterrows():
        ring = [[round(lon, 5), round(lat, 5)] for lat, lon in h3.cell_to_boundary(sid)]
        ring.append(ring[0])
        props = {
            "id": sid,
            "canopy": r(row["canopy_frac_latest"], 3),
            "canopy0": r(row["canopy_frac_baseline"], 3),
            "imperv": r(row["impervious_frac"], 3),
            "lc": row["land_cover_class"],
            "elev": r(row["elevation_m"], 1),
            "pop": r(row["population"], 0),
            "vuln": r(row["vulnerable_residents"], 0),
            "trees": r(row["existing_tree_count"], 0),
            "planted": int(planted_all.get(sid, 0)),
            "planted_w": int(planted_window.get(sid, 0)),
            "heat": r(heat.get(sid), 2),
            "heat_n": int(heat_n.get(sid, 0)),
        }
        if sid in rc.index:
            x = rc.loc[sid]
            props.update({
                "rank": int(x["rank"]), "score": r(x["score"], 5),
                "c5": r(x["predicted_cooling_k_5y"], 3), "c5lo": r(x["predicted_cooling_k_5y_low"], 3),
                "c5hi": r(x["predicted_cooling_k_5y_high"], 3),
                "c15": r(x["predicted_cooling_k_15y"], 3), "c15lo": r(x["predicted_cooling_k_15y_low"], 3),
                "c15hi": r(x["predicted_cooling_k_15y_high"], 3),
                "cost": r(x["est_cost_usd"], 0), "kind": x["suggested_intervention"],
                "holdout": bool(x["holdout_control"]), "rec_vuln": r(x["vulnerable_residents"], 0),
            })
        if sid in e.index:
            x = e.loc[sid]
            direction = "cooling" if x["effect_k"] < 0 else "warming"
            props.update({
                "eff": r(x["effect_k"], 3), "eff_lo": r(x["ci_low_k"], 3), "eff_hi": r(x["ci_high_k"], 3),
                "mde": r(x["mde_k"], 2), "pval": r(x["placebo_p"], 3),
                "label": x["quality_label"],
                "outcome": f"detected_{direction}" if x["quality_label"] == "detected" else x["quality_label"],
                "dose": int(x["dose_trees"]), "t_year": int(x["treatment_year"]),
                "n_pre": int(x["n_pre_scenes"]), "n_post": int(x["n_post_scenes"]), "n_ctrl": int(x["n_controls"]),
            })
        features.append({"type": "Feature", "id": len(features),
                         "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": props})

    (OUT / f"{city}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features},
                                                    separators=(",", ":")))

    # Per-site detail that would bloat the map file: plantings per year and the
    # yearly mean of the evaluated site's temperature against its controls.
    s = series[series["city_id"] == city].copy()
    s["year"] = pd.to_datetime(s["scene_date"]).dt.year
    yearly = s.groupby(["site_id", "year"]).agg(site=("site_temp_rel_k", "mean"),
                                               ctrl=("control_temp_rel_k", "mean"),
                                               n=("site_temp_rel_k", "size")).reset_index()
    site_series = {sid: [[int(y), r(a, 3), r(b, 3), int(n)] for y, a, b, n in
                         zip(g["year"], g["site"], g["ctrl"], g["n"])]
                   for sid, g in yearly.groupby("site_id")}
    (OUT / f"{city}_detail.json").write_text(json.dumps(
        {"planted_by_year": by_year, "series": site_series}, separators=(",", ":")))

    # Small file for the landing page hero: cell centre and heat only.
    hero = [[round(row["centroid_lon"], 4), round(row["centroid_lat"], 4), r(heat.get(sid), 2)]
            for sid, row in f.iterrows()]
    (OUT / f"{city}_hero.json").write_text(json.dumps(hero, separators=(",", ":")))

    labels = e["quality_label"].value_counts()
    detected = e[e["quality_label"] == "detected"]
    years = iv.groupby("plant_year")["trees_planted"].sum()
    return {
        "city_id": city,
        "cells": int(len(f)),
        "bounds": [round(f["centroid_lon"].min(), 4), round(f["centroid_lat"].min(), 4),
                   round(f["centroid_lon"].max(), 4), round(f["centroid_lat"].max(), 4)],
        "population": int(f["population"].sum()),
        "trees_dated": int(iv["trees_planted"].sum()),
        "plant_years": [int(years.index.min()), int(years.index.max())],
        "planted_by_year": {int(y): int(n) for y, n in years.items()},
        "sites_evaluated": int(len(e)),
        "detected": int(labels.get("detected", 0)),
        "detected_cooling": int((detected["effect_k"] < 0).sum()),
        "detected_warming": int((detected["effect_k"] >= 0).sum()),
        "inconclusive": int(labels.get("inconclusive", 0)),
        "not_detectable": int(labels.get("not_detectable", 0)),
        "mde_median_k": r(e["mde_k"].median(), 2),
        "effect_mean_k": r(e["effect_k"].mean(), 3),
        "candidates": int(len(rc)),
        "holdouts": int(rc["holdout_control"].sum()) if len(rc) else 0,
        "heat_scenes": int(heat_scenes),
        "heat_from_year": HEAT_FROM_YEAR,
        "panel_rows": int(len(panel)),
        "panel_scenes": int(panel["scene_id"].nunique()),
        "panel_years": [int(panel["year"].min()), int(panel["year"].max())],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default="demo/data_real")
    ap.add_argument("--panel-dir", default="data/panel")
    args = ap.parse_args()
    snap, panel_dir = ROOT / args.snapshot, ROOT / args.panel_dir
    OUT.mkdir(parents=True, exist_ok=True)

    config = yaml.safe_load((ROOT / "config" / "us" / "config.yaml").read_text())
    feats = pd.read_parquet(snap / "silver_features.parquet")
    ints = pd.read_parquet(snap / "silver_interventions.parquet")
    effects = pd.read_parquet(snap / "gold_site_effects.parquet")
    recs = pd.read_parquet(snap / "gold_recommendations.parquet")
    series = pd.read_parquet(snap / "panel_sample.parquet")

    cities = []
    for c in config["cities"]:
        city = c["city_id"]
        panel = pd.read_parquet(panel_dir / f"{city}_silver_panel.parquet",
                                columns=["site_id", "scene_id", "year", "sensor", "lst_median_k",
                                         "is_clear", "city_clear_frac"])
        summary = build_city(city, feats, ints, effects, recs, series, panel)
        summary.update({"name": c["name"], "center": [c["center"]["lon"], c["center"]["lat"]],
                        "lead": bool(c.get("lead", False))})
        cities.append(summary)
        print(f"{city}: {summary['cells']} cells, {summary['sites_evaluated']} evaluated, "
              f"{summary['candidates']} candidates, heat from {summary['heat_scenes']} scenes")

    meta = {
        "display": config["display"],
        "costs_usd": config["costs_usd"],
        "horizons_years": config["horizons_years"],
        "treatment_window": list(TREATMENT_WINDOW),
        "method_version": str(effects["method_version"].iloc[0]),
        "model_version": str(recs["model_version"].iloc[0]),
        "panel_version": str(effects["panel_version"].iloc[0]),
        "cities": cities,
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
