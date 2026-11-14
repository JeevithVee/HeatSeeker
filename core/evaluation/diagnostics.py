"""Specification, temporal and pre-cohort diagnostics; never alter headline gold.

Point estimates reuse the production matcher/DiD. Resampling diagnostics omit the
per-site bootstrap to keep year-by-year rematching inexpensive. None identifies a
causal effect or supplies calibrated multiway-cluster confidence intervals.
"""

from dataclasses import replace

import numpy as np
import pandas as pd

from core.evaluation.did import site_did
from core.evaluation.inference import placebo_distribution
from core.evaluation.matching import match_controls
from core.evaluation.panel import filter_scenes, relative_temperature, to_wide, yearly_means
from core.evaluation.pooled import pooled_block_sensitivity
from core.evaluation.treatment import eligible_cells, treatment_table

DIAGNOSTICS_VERSION = "1.0.0"
METRICS = {"overall": "effect_k", "five_year_plus": "five_year_plus_k"}
POINT_COLUMNS = ["site_id", "treatment_year", "effect_k", "five_year_plus_k",
                 "n_pre_scenes", "n_post_scenes", "n_controls"]


def point_estimates(wide, years, treated, controls, features, cfg):
    """Production point estimates and fixed matches, without per-site inference."""
    if wide.empty or not wide.shape[1]:
        return pd.DataFrame(columns=POINT_COLUMNS), {}
    treated = treated.loc[treated.site_id.isin(wide.index)]
    matches = match_controls(treated, controls, features, yearly_means(wide, years), cfg)
    W = wide.to_numpy(dtype=float)
    index = {s: i for i, s in enumerate(wide.index)}
    rows = []
    for t in treated.itertuples(index=False):
        control_ids = matches.get(t.site_id, [])
        Yc = W[[index[c] for c in control_ids]] if control_ids else np.empty((0, W.shape[1]))
        estimate = site_did(W[index[t.site_id]], Yc, years, int(t.treatment_year), cfg)
        late = [value for year, value in estimate.event_study.items() if year >= 5]
        rows.append({"site_id": t.site_id, "treatment_year": int(t.treatment_year),
                     "effect_k": estimate.effect_k, "five_year_plus_k": float(np.mean(late)) if late else np.nan,
                     "n_pre_scenes": estimate.n_pre, "n_post_scenes": estimate.n_post,
                     "n_controls": len(control_ids)})
    return pd.DataFrame(rows, columns=POINT_COLUMNS), matches


def supported(points, cfg, metric="overall"):
    if points.empty:
        return pd.Series(dtype=float, index=pd.Index([], name="site_id"))
    column = METRICS[metric]
    keep = ((points.n_pre_scenes >= cfg.min_pre_scenes) & (points.n_post_scenes >= cfg.min_post_scenes)
            & (points.n_controls >= cfg.min_controls) & np.isfinite(points[column]))
    return points.loc[keep].set_index("site_id")[column]


def summary(points, cfg):
    return {metric: {"n_sites": len(values), "mean_effect_k": float(values.mean()) if len(values) else None}
            for metric in METRICS for values in [supported(points, cfg, metric)]}


def year_block_sensitivity(wide, years, treated, controls, features, cfg,
                           baseline=None, min_common_fraction=0.8):
    """Drop each calendar year and rematch; estimate intervals on a common cohort.

    Unsupported cells are not silently removed from individual replicates. The
    common cohort must retain >=80% of baseline support, or no interval is given.
    """
    if baseline is None:
        baseline, _ = point_estimates(wide, years, treated, controls, features, cfg)
    folds = {}
    for year in np.unique(years):
        keep = years != year
        fold = wide.loc[:, keep].dropna(how="all")
        folds[int(year)] = point_estimates(fold, years[keep], treated, controls, features, cfg)[0]
    report = {"method": "delete_one_calendar_year_with_rematching", "rematched": True,
              "limitations": "Common-cohort normal-approximation sensitivity; few years and unmodelled dependence remain."}
    cohorts = {}
    for metric in METRICS:
        base = supported(baseline, cfg, metric)
        common = base.index
        fold_values = {year: supported(points, cfg, metric) for year, points in folds.items()}
        for values in fold_values.values():
            common = common.intersection(values.index)
        cohorts[metric] = common
        fraction = len(common) / max(len(base), 1)
        point = float(base.loc[common].mean()) if len(common) else None
        deleted = np.array([v.loc[common].mean() for v in fold_values.values()], dtype=float)
        sufficient = (len(common) >= 2 and len(deleted) >= 4 and fraction >= min_common_fraction
                      and np.isfinite(deleted).all())
        se = float(np.sqrt((len(deleted) - 1) / len(deleted) * ((deleted - deleted.mean()) ** 2).sum())) if sufficient else None
        report[metric] = {"status": "sensitivity_only" if sufficient else "insufficient_common_support",
                          "n_baseline_sites": len(base), "n_common_sites": len(common),
                          "common_retained_fraction": fraction, "n_years": len(deleted),
                          "mean_effect_k": point, "se_k": se,
                          "normal_interval_low_k": point - 1.96 * se if se is not None else None,
                          "normal_interval_high_k": point + 1.96 * se if se is not None else None,
                          "delete_one_year": [{"year": year, "n_supported_sites": len(values),
                                               "mean_common_cohort_k": float(values.loc[common].mean()) if len(common) else None,
                                               "mean_all_supported_k": float(values.mean()) if len(values) else None}
                                              for year, values in fold_values.items()]}
    return report, cohorts


def combine_components(point, spatial_se, year_se):
    """Add both components. This is an explicit sensitivity construction, not CGM."""
    total = spatial_se + year_se
    return {"mean_effect_k": point, "spatial_se_k": spatial_se, "year_se_k": year_se,
            "se_sum_k": total, "sensitivity_low_k": point - 1.96 * total,
            "sensitivity_high_k": point + 1.96 * total}


def combined_space_year(wide, years, baseline, matches, features, cfg, temporal, cohorts):
    """Combine components evaluated on the same cohort and centred on the same point."""
    result = {"method": "sum_of_spatial_and_year_SE_sensitivity", "metrics": {},
              "limitations": "Adds SEs rather than selecting the wider component. This permits positive covariance "
              "in an additive-component interpretation, but is not a calibrated multiway variance estimator. "
              "Components can overlap; source-block dependence and observational bias remain."}
    cache = {}
    for metric in METRICS:
        year = temporal[metric]
        if year["status"] != "sensitivity_only":
            result["metrics"][metric] = {"status": "insufficient_common_support", "grids": []}
            continue
        ids = cohorts[metric]
        key = tuple(sorted(ids))
        if key not in cache:
            common_points = baseline.loc[baseline.site_id.isin(ids)]
            common_matches = {sid: matches[sid] for sid in ids if sid in matches}
            cache[key] = pooled_block_sensitivity(wide, years, common_points, common_matches, features, cfg)
        grids = []
        for grid in cache[key].get("grids", []):
            spatial = grid[metric]
            item = {"block_size_m": grid["block_size_m"], "origin_offset_fraction": grid["origin_offset_fraction"],
                    "status": spatial["status"], "n_sites": spatial["n_sites"]}
            if spatial["se_k"] is not None:
                if not np.isclose(spatial["mean_effect_k"], year["mean_effect_k"], atol=1e-10, rtol=1e-10):
                    raise ValueError("Spatial and temporal components must use the same cohort/estimand")
                item.update(combine_components(year["mean_effect_k"], spatial["se_k"], year["se_k"]))
            grids.append(item)
        result["metrics"][metric] = {"status": "sensitivity_only", "grids": grids}
    return result


def fake_date_diagnostic(panel, features, interventions, cfg, variant="all"):
    """Pretend the recorded treatment-window cohort was planted in 2010, L5 2008–11 only."""
    fake_cfg = replace(cfg, sensors=("LANDSAT_5",))
    date = pd.to_datetime(panel.acquired_at_utc, utc=True)
    raw = panel.loc[date.dt.year.between(2008, 2011) & panel.sensor.eq("LANDSAT_5")]
    p = relative_temperature(filter_scenes(raw, fake_cfg), fake_cfg) if not raw.empty else pd.DataFrame()
    scenes = p.drop_duplicates("scene_id") if not p.empty else pd.DataFrame()
    pre = int((scenes.scene_year < 2010).sum()) if not scenes.empty else 0
    post = int((scenes.scene_year > 2010).sum()) if not scenes.empty else 0
    report = {"method": "same_sensor_pre_cohort_fake_date", "sensor": "LANDSAT_5",
              "years": [2008, 2009, 2010, 2011], "fake_treatment_year": 2010,
              "n_pre_scenes": pre, "n_post_scenes": post,
              "limitations": "Thin older-sensor window, one post year. Tests a period before the recorded cohort, "
              "not a treeless city. A nonzero contrast challenges causal attribution but does not measure headline bias."}
    if pre < cfg.min_pre_scenes or post < cfg.min_post_scenes:
        return {**report, "status": "insufficient_same_sensor_scenes"}
    wide, years = to_wide(p)
    eligible = wide.index.intersection(eligible_cells(features, cfg))
    treated, controls = treatment_table(interventions, eligible, cfg, variant)
    fake = treated.assign(treatment_year=2010)
    points, matches = point_estimates(wide, years, fake, controls, features, fake_cfg)
    report["pooled"] = summary(points, fake_cfg)
    if report["pooled"]["overall"]["n_sites"] < 2:
        return {**report, "status": "insufficient_site_support"}
    report["source_block_sensitivity"] = pooled_block_sensitivity(wide, years, points, matches, features, fake_cfg)
    static_points, _ = point_estimates(wide, years, fake, controls, features, replace(fake_cfg, pretrend_weight=0.0))
    report["no_pre_outcome_matching"] = summary(static_points, fake_cfg)
    placebo = placebo_distribution(controls, fake.treatment_year.to_numpy(), features, yearly_means(wide, years),
                                    wide, years, np.random.default_rng(cfg.seed), fake_cfg,
                                    treated_ids=pd.Index(fake.site_id))
    report["n_control_placebos"] = len(placebo)
    report["control_placebo_mean_k"] = float(placebo.mean()) if len(placebo) else None
    intervals = [g["overall"] for g in report["source_block_sensitivity"].get("grids", [])
                 if g["overall"]["se_k"] is not None]
    nonzero = any(g["normal_interval_low_k"] > 0 or g["normal_interval_high_k"] < 0 for g in intervals)
    return {**report, "status": "nonzero_pre_cohort_contrast" if nonzero else "diagnostic_only_no_clear_rejection"}


def sensor_family_diagnostic(filtered_panel, treated, cfg):
    scenes = filtered_panel.drop_duplicates("scene_id").copy()
    families = {"LANDSAT_5": "legacy_5_7", "LANDSAT_7": "legacy_5_7",
                "LANDSAT_8": "modern_8_9", "LANDSAT_9": "modern_8_9"}
    scenes["family"] = scenes.sensor.map(families).fillna(scenes.sensor)
    rows = []
    for year in sorted(treated.treatment_year.unique()):
        pre = scenes.loc[scenes.scene_year < year, "family"].value_counts().to_dict()
        post = scenes.loc[scenes.scene_year >= year + cfg.post_start_offset, "family"].value_counts().to_dict()
        rows.append({"treatment_year": int(year), "pre_scenes_by_family": pre, "post_scenes_by_family": post,
                     "families_present_only_pre": sorted(set(pre) - set(post)),
                     "families_present_only_post": sorted(set(post) - set(pre))})
    transition = any(row["families_present_only_pre"] or row["families_present_only_post"] for row in rows)
    return {"sensor_transition_sensitive": transition, "cohorts": rows,
            "interpretation": "Cross-sensor sensitivity is not independent confirmation; scene differencing does not remove family-specific spatial contrast changes."}


def review_diagnostics(panel, features, interventions, cfg, variant="all"):
    p = relative_temperature(filter_scenes(panel, cfg), cfg)
    wide, years = to_wide(p)
    eligible = wide.index.intersection(eligible_cells(features, cfg))
    treated, controls = treatment_table(interventions, eligible, cfg, variant)
    baseline, matches = point_estimates(wide, years, treated, controls, features, cfg)
    static, _ = point_estimates(wide, years, treated, controls, features, replace(cfg, pretrend_weight=0.0))
    comparison = {"headline": summary(baseline, cfg), "no_pre_outcome_matching": summary(static, cfg),
                  "interpretation": "Specification sensitivity, not a correction or a separately identified causal estimate."}
    comparison["common_cohort"] = {}
    for metric in METRICS:
        a, b = supported(baseline, cfg, metric), supported(static, cfg, metric)
        ids = a.index.intersection(b.index)
        comparison["common_cohort"][metric] = {"n_sites": len(ids),
            "headline_mean_k": float(a.loc[ids].mean()) if len(ids) else None,
            "static_only_mean_k": float(b.loc[ids].mean()) if len(ids) else None}
    temporal, cohorts = year_block_sensitivity(wide, years, treated, controls, features, cfg, baseline)
    later = interventions.loc[interventions.site_id.isin(treated.site_id)
                              & interventions.plant_year.gt(cfg.treatment_window[1])]
    return {"diagnostics_version": DIAGNOSTICS_VERSION, "variant": variant,
            "specification_comparison": comparison, "year_block_sensitivity": temporal,
            "combined_space_year_sensitivity": combined_space_year(wide, years, baseline, matches, features, cfg, temporal, cohorts),
            "pre_cohort_fake_date": fake_date_diagnostic(panel, features, interventions, cfg, variant),
            "sensor_family_support": sensor_family_diagnostic(p, treated, cfg),
            "later_planting_context": {"treated_cells_with_post_window_plantings": int(later.site_id.nunique()),
                                       "trees_after_window_in_treated_cells": int(later.trees_planted.sum()),
                                       "interpretation": "Post-period differences can include later plantings; dose_trees only counts the treatment window."},
            "inference_status": "observational_association_not_established_causal_cooling"}
