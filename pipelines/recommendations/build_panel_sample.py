"""Build the app's per-site scene series from silver.panel.

    python pipelines/recommendations/build_panel_sample.py \
        --panel nyc_silver_panel.parquet \
        --site-effects gold_site_effects.parquet \
        --interventions silver_interventions.csv \
        --out panel_sample.parquet

One row per evaluated site per usable scene: the site's LST relative to the
city baseline, next to the control pool's mean relative LST. Filters follow
Agent 3's rules (Landsat only, city_clear_frac >= 0.5, is_clear cells).

The control series is the CONTROL-POOL MEAN (cells with <= 2 trees ever),
not the site's own matched controls - good enough for the app's chart; the
estimate itself comes from gold.site_effects, which does use matched
controls.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def read_any(path: str) -> pd.DataFrame:
    p = Path(path)
    return pd.read_csv(p) if p.suffix == ".csv" else pd.read_parquet(p)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    ap.add_argument("--site-effects", required=True)
    ap.add_argument("--interventions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-control-trees", type=int, default=2)
    args = ap.parse_args()

    panel = read_any(args.panel)
    effects = read_any(args.site_effects)
    effects = effects[effects["variant"] == "all"]
    interventions = read_any(args.interventions)

    usable = panel[
        panel["sensor"].str.startswith("LANDSAT")
        & (panel["city_clear_frac"] >= 0.5)
        & panel["is_clear"]
    ].copy()

    baseline = usable.groupby("scene_id")["lst_median_k"].median().rename("baseline_k")
    usable = usable.join(baseline, on="scene_id")
    usable["rel_k"] = usable["lst_median_k"] - usable["baseline_k"]

    planted_total = interventions.groupby("site_id")["trees_planted"].sum()
    control_ids = set(planted_total[planted_total <= args.max_control_trees].index) | (
        set(usable["site_id"]) - set(planted_total.index)
    )
    control = (
        usable[usable["site_id"].isin(control_ids)]
        .groupby("scene_id")["rel_k"].mean().rename("control_temp_rel_k")
    )

    sites = usable[usable["site_id"].isin(set(effects["site_id"]))].copy()
    sites = sites.join(control, on="scene_id")
    sites["scene_date"] = pd.to_datetime(sites["acquired_at_utc"]).dt.date.astype(str)
    sites = sites.merge(
        effects[["site_id", "treatment_year"]].drop_duplicates("site_id"),
        on="site_id")
    sites["post"] = pd.to_datetime(sites["scene_date"]).dt.year >= sites["treatment_year"]

    out = sites.rename(columns={"rel_k": "site_temp_rel_k"})[[
        "country_code", "city_id", "site_id", "scene_date",
        "site_temp_rel_k", "control_temp_rel_k", "post",
    ]].sort_values(["site_id", "scene_date"])
    out.to_parquet(args.out, index=False)
    print(f"panel_sample: {len(out)} rows, {out['site_id'].nunique()} sites, "
          f"{out['scene_date'].nunique()} scene dates -> {args.out}")


if __name__ == "__main__":
    main()
