"""Run the full evaluation for one city and return rows in the gold.site_effects schema."""

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from core.evaluation.config import EvalConfig
from core.evaluation.did import site_did
from core.evaluation.inference import bootstrap_effect, placebo_distribution, placebo_p_value
from core.evaluation.labels import quality_label
from core.evaluation.matching import match_controls
from core.evaluation.panel import filter_scenes, relative_temperature, to_wide, yearly_means
from core.evaluation.treatment import eligible_cells, treatment_table

GOLD_COLUMNS = [
    "country_code", "city_id", "site_id", "variant", "treatment_year", "intervention_type", "dose_trees",
    "n_pre_scenes", "n_post_scenes", "n_controls", "effect_k", "effect_se_k", "ci_low_k", "ci_high_k",
    "placebo_p", "mde_k", "quality_label", "event_study_json", "panel_version", "method_version",
    "evaluated_at_utc",
]


def evaluate_city(
    panel: pd.DataFrame,
    features: pd.DataFrame,
    interventions: pd.DataFrame,
    cfg: EvalConfig = EvalConfig(),
    variant: str = "all",
    panel_version: str | None = None,
) -> pd.DataFrame:
    """gold.site_effects rows for one city and one variant."""
    return evaluate_city_with_report(panel, features, interventions, cfg, variant, panel_version)[0]


def evaluate_city_with_report(
    panel: pd.DataFrame,
    features: pd.DataFrame,
    interventions: pd.DataFrame,
    cfg: EvalConfig = EvalConfig(),
    variant: str = "all",
    panel_version: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Same as evaluate_city, plus the sanity report (see report.py)."""
    from core.evaluation import METHOD_VERSION
    from core.evaluation.report import build_report

    rng = np.random.default_rng(cfg.seed)
    country_code = str(panel["country_code"].iloc[0])
    city_id = str(panel["city_id"].iloc[0])

    p = relative_temperature(filter_scenes(panel, cfg), cfg)
    wide, scene_year = to_wide(p)
    yearly = yearly_means(wide, scene_year)
    W = wide.to_numpy(dtype=float)
    row = {sid: i for i, sid in enumerate(wide.index)}

    eligible = wide.index.intersection(eligible_cells(features, cfg))
    treated, control_ids = treatment_table(interventions, eligible, cfg, variant)
    matches = match_controls(treated, control_ids, features, yearly, cfg)

    placebo = placebo_distribution(
        control_ids, treated["treatment_year"].to_numpy(), features, yearly, wide, scene_year, rng, cfg,
        treated_ids=pd.Index(treated["site_id"]),
    )
    # Honest detection floor. A site is called detected when |effect| beats the placebo 95th
    # percentile, so 80% power against an effect delta needs delta ~ q95 + 0.84 * placebo SD.
    # The bootstrap SE alone misses the drift unplanted cells show on their own.
    placebo_floor = (
        float(np.quantile(np.abs(placebo), 1 - cfg.alpha) + 0.84 * np.std(placebo, ddof=1))
        if len(placebo) > 10 else 0.0
    )

    now = pd.Timestamp(datetime.now(timezone.utc)).floor("s")
    rows = []
    for t in treated.itertuples(index=False):
        ctrls = matches.get(t.site_id, [])
        y_t = W[row[t.site_id]]
        Y_c = W[[row[c] for c in ctrls]] if ctrls else np.empty((0, W.shape[1]))
        est = site_did(y_t, Y_c, scene_year, int(t.treatment_year), cfg)
        se, lo, hi = bootstrap_effect(y_t, Y_c, est.pre_mask, est.post_mask, rng, cfg)
        mde = max(cfg.power_z * se, placebo_floor) if not np.isnan(se) else float("nan")
        pp = placebo_p_value(est.effect_k, placebo)
        label = quality_label(est.effect_k, lo, hi, pp, mde, est.n_pre, est.n_post, len(ctrls), cfg)
        rows.append({
            "country_code": country_code, "city_id": city_id, "site_id": t.site_id, "variant": variant,
            "treatment_year": int(t.treatment_year), "intervention_type": t.intervention_type,
            "dose_trees": int(t.dose_trees), "n_pre_scenes": est.n_pre, "n_post_scenes": est.n_post,
            "n_controls": len(ctrls), "effect_k": est.effect_k, "effect_se_k": se, "ci_low_k": lo,
            "ci_high_k": hi, "placebo_p": pp, "mde_k": mde, "quality_label": label,
            "event_study_json": json.dumps({str(k): round(v, 4) for k, v in sorted(est.event_study.items())}),
            "panel_version": panel_version, "method_version": METHOD_VERSION, "evaluated_at_utc": now,
        })
    gold = pd.DataFrame(rows, columns=GOLD_COLUMNS)
    report = build_report(gold, p, pd.Index(treated["site_id"]), matches, features, placebo, cfg)
    report["variant"] = variant
    return gold, report


def evaluate_city_all_variants(panel, features, interventions, cfg: EvalConfig = EvalConfig(), panel_version=None):
    parts = [evaluate_city(panel, features, interventions, cfg, v, panel_version) for v in ("all", "excl_batch_dated")]
    return pd.concat(parts, ignore_index=True)


def evaluate_city_all_variants_with_reports(panel, features, interventions, cfg: EvalConfig = EvalConfig(), panel_version=None):
    """Returns (gold for both variants, {variant: report})."""
    golds, reports = [], {}
    for v in ("all", "excl_batch_dated"):
        g, r = evaluate_city_with_report(panel, features, interventions, cfg, v, panel_version)
        golds.append(g)
        reports[v] = r
    return pd.concat(golds, ignore_index=True), reports
