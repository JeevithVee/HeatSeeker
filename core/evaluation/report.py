"""Sanity report that accompanies every gold.site_effects run.

Answers the questions a reviewer asks before trusting the effects:
  * How many scenes survived filtering, per year?
  * Are treated cells and their matched controls balanced on the matching variables?
  * Is the pre-period flat? (mean event-study value at negative years, pooled over sites)
  * Does the placebo distribution centre on zero, and how wide is it?
  * Label counts and median MDE.
"""

import json

import numpy as np
import pandas as pd

from core.evaluation.config import EvalConfig


def standardized_mean_differences(
    treated_ids: pd.Index, matches: dict[str, list[str]], features: pd.DataFrame, cfg: EvalConfig
) -> pd.DataFrame:
    """SMD = (mean_treated − mean_controls) / pooled SD, per matching variable. |SMD| < 0.1 is good."""
    feats = features.set_index("site_id") if "site_id" in features.columns else features
    vars_ = [v for v in cfg.match_vars if v in feats.columns and feats[v].notna().any()]
    t_ids = [s for s in treated_ids if s in matches]
    if not t_ids or not vars_:
        return pd.DataFrame(columns=["variable", "mean_treated", "mean_controls", "smd"])
    c_ids = [c for s in t_ids for c in matches[s]]
    T, C = feats.loc[t_ids, vars_], feats.loc[c_ids, vars_]
    pooled = np.sqrt((T.var(ddof=0) + C.var(ddof=0)) / 2).replace(0, np.nan)
    out = pd.DataFrame({
        "variable": vars_, "mean_treated": T.mean().to_numpy(), "mean_controls": C.mean().to_numpy(),
        "smd": ((T.mean() - C.mean()) / pooled).to_numpy(),
    })
    return out.reset_index(drop=True)


def pooled_event_study(gold: pd.DataFrame) -> pd.DataFrame:
    """Mean and site count of the event-study effect by years since planting, across sites."""
    rows = []
    for s in gold["event_study_json"].dropna():
        for k, v in json.loads(s).items():
            rows.append((int(k), float(v)))
    if not rows:
        return pd.DataFrame(columns=["years_since", "mean_effect_k", "n_sites"])
    df = pd.DataFrame(rows, columns=["years_since", "effect_k"])
    return (df.groupby("years_since")["effect_k"].agg(mean_effect_k="mean", n_sites="size")
            .reset_index().sort_values("years_since"))


DOSE_BINS = [10, 15, 20, 30, 50, 10_000]


def pre_trend_diagnostics(gold):
    """Descriptive pre-period slopes, not the identically centred pre mean."""
    slopes, contrasts = [], []
    for raw in gold["event_study_json"].dropna():
        pre = sorted((int(k), float(v)) for k, v in json.loads(raw).items() if int(k) < 0)
        if len(pre) >= 3:
            x, y = np.asarray(pre, dtype=float).T
            slopes.append(float(np.sum((x - x.mean()) * (y - y.mean())) / np.sum((x - x.mean()) ** 2)))
            contrasts.append(float(y[-1] - y[0]))
    return {"n_sites_with_three_pre_years": len(slopes),
            "mean_slope_k_per_year": float(np.mean(slopes)) if slopes else None,
            "median_slope_k_per_year": float(np.median(slopes)) if slopes else None,
            "mean_last_minus_first_pre_year_k": float(np.mean(contrasts)) if contrasts else None,
            "limitations": "Descriptive only; matching uses these same pre-period data, so this is not an independent parallel-trends test."}


def pooled_by_dose(gold: pd.DataFrame, min_years: int = 5) -> pd.DataFrame:
    """Pooled effect by trees-in-cell bin: mean effect_k with SE across sites, and the mean
    event-study effect at >= min_years since planting. Sites are treated as independent."""
    if gold.empty:
        return pd.DataFrame(columns=["dose_bin", "n_sites", "mean_effect_k", "se_k", "mean_effect_5yr_plus_k", "se_5yr_plus_k"])
    g = gold.copy()
    late = []
    for s in g["event_study_json"].fillna("{}"):
        vals = [v for k, v in json.loads(s).items() if int(k) >= min_years]
        late.append(float(np.mean(vals)) if vals else np.nan)
    g["late"] = late
    g["dose_bin"] = pd.cut(g["dose_trees"], DOSE_BINS, right=False,
                           labels=[f"{a}-{b - 1}" if b < 10_000 else f"{a}+" for a, b in zip(DOSE_BINS[:-1], DOSE_BINS[1:])])
    rows = []
    for b, s in g.groupby("dose_bin", observed=True):
        e, l = s["effect_k"].dropna(), s["late"].dropna()
        rows.append({
            "dose_bin": str(b), "n_sites": int(len(s)),
            "mean_effect_k": float(e.mean()) if len(e) else np.nan,
            "se_k": float(e.std(ddof=1) / np.sqrt(len(e))) if len(e) > 1 else np.nan,
            "mean_effect_5yr_plus_k": float(l.mean()) if len(l) else np.nan,
            "se_5yr_plus_k": float(l.std(ddof=1) / np.sqrt(len(l))) if len(l) > 1 else np.nan,
        })
    all_e, all_l = g["effect_k"].dropna(), g["late"].dropna()
    rows.append({
        "dose_bin": "all", "n_sites": int(len(g)),
        "mean_effect_k": float(all_e.mean()), "se_k": float(all_e.std(ddof=1) / np.sqrt(len(all_e))),
        "mean_effect_5yr_plus_k": float(all_l.mean()) if len(all_l) else np.nan,
        "se_5yr_plus_k": float(all_l.std(ddof=1) / np.sqrt(len(all_l))) if len(all_l) > 1 else np.nan,
    })
    return pd.DataFrame(rows)


def build_report(
    gold: pd.DataFrame,
    filtered_panel: pd.DataFrame,
    treated_ids: pd.Index,
    matches: dict[str, list[str]],
    features: pd.DataFrame,
    placebo: np.ndarray,
    cfg: EvalConfig,
    wide=None,
    scene_year=None,
    control_ids=None,
) -> dict:
    scenes = filtered_panel.drop_duplicates("scene_id")
    scenes_per_year = scenes.groupby("scene_year").size().to_dict()
    es = pooled_event_study(gold)
    pre = es.loc[es["years_since"] < 0]
    pre_mean = float(np.average(pre["mean_effect_k"], weights=pre["n_sites"])) if len(pre) else float("nan")
    balance = standardized_mean_differences(treated_ids, matches, features, cfg)
    det = gold.loc[gold["quality_label"] == "detected", "effect_k"]
    from core.evaluation.pooled import pooled_block_sensitivity, control_reuse
    report = {
        # Multiple testing: with n sites and a 5% placebo test, about alpha*n would be called
        # detected under the null. Compare n_detected with this before celebrating.
        "n_detected": int(len(det)),
        "n_detected_cooling": int((det < 0).sum()),
        "n_detected_warming": int((det > 0).sum()),
        "expected_detected_under_null": float(cfg.alpha * len(gold)),
        "n_scenes": int(len(scenes)),
        "scenes_per_year": {int(k): int(v) for k, v in scenes_per_year.items()},
        "n_cells_in_panel": int(filtered_panel["site_id"].nunique()),
        "n_treated": int(len(treated_ids)),
        "n_matched": int(sum(1 for s in treated_ids if s in matches)),
        "n_controls_eligible": len(control_ids) if control_ids is not None else None,
        "control_reuse": control_reuse(matches),
        "labels": gold["quality_label"].value_counts().to_dict(),
        "median_mde_k": float(gold["mde_k"].median()) if len(gold) else float("nan"),
        "median_effect_k_detected": float(gold.loc[gold["quality_label"] == "detected", "effect_k"].median())
        if (gold["quality_label"] == "detected").any() else float("nan"),
        "pre_period_mean_effect_k": pre_mean,                 # should be ~0
        "max_abs_smd": float(balance["smd"].abs().max()) if len(balance) else float("nan"),   # < 0.1 good, < 0.25 ok
        "balance": balance.round(4).to_dict("records"),
        "placebo_mean_k": float(np.mean(placebo)) if len(placebo) else float("nan"),
        "n_valid_placebo_estimates": len(placebo),
        "placebo_sd_k": float(np.std(placebo, ddof=1)) if len(placebo) > 1 else float("nan"),
        "placebo_q95_abs_k": float(np.quantile(np.abs(placebo), 0.95)) if len(placebo) else float("nan"),
        "event_study": es.round(4).to_dict("records"),
        "pre_trend_diagnostics": pre_trend_diagnostics(gold),
        "pooled_by_dose": pooled_by_dose(gold).round(4).to_dict("records"),
        "pooled_iid_se_warning": "Across-site SEs assume independence; use source-block sensitivity and its limitations.",
        "pre_period_mean_warning": "Pre-period centering makes the pooled pre mean approximately zero by construction; this is not a parallel-trends test.",
    }
    if wide is not None and scene_year is not None:
        report["pooled_block_sensitivity"] = pooled_block_sensitivity(wide, scene_year, gold, matches, features, cfg)
    return report


def cfg_alpha(rep: dict) -> str:
    n = max(rep.get("n_treated", 0), 1)
    return f"{rep.get('expected_detected_under_null', 0.0) / n:.2f}"


def format_report(rep: dict) -> str:
    lines = [
        f"scenes kept: {rep['n_scenes']} over {len(rep['scenes_per_year'])} years; cells: {rep['n_cells_in_panel']:,}",
        f"treated: {rep['n_treated']:,} (matched {rep['n_matched']:,}); labels: {rep['labels']}",
        f"detected: {rep['n_detected']} ({rep['n_detected_cooling']} cooling, {rep['n_detected_warming']} warming) "
        f"vs alpha*n={rep['expected_detected_under_null']:.0f} (reference, not calibrated expected count); alpha={cfg_alpha(rep)}",
        f"median MDE {rep['median_mde_k']:.2f} K; median detected effect {rep['median_effect_k_detected']:.2f} K",
        f"pre-period pooled effect {rep['pre_period_mean_effect_k']:+.3f} K (centred by construction; not a pre-trend test)",
        f"control balance: max |SMD| {rep['max_abs_smd']:.3f} (want < 0.1)",
        f"placebo: mean {rep['placebo_mean_k']:+.3f} K, sd {rep['placebo_sd_k']:.3f} K, 95% |q| {rep['placebo_q95_abs_k']:.3f} K",
        "event study (years since planting: mean K, n): "
        + ", ".join(f"{r['years_since']}: {r['mean_effect_k']:+.2f} ({r['n_sites']})" for r in rep["event_study"]),
        "pooled by trees in cell (mean effect ± independence-assuming SE; at 5+ years ± SE; n):",
    ]
    for r in rep.get("pooled_by_dose", []):
        lines.append(
            f"  {r['dose_bin']:>6}: {r['mean_effect_k']:+.3f} ± {r['se_k']:.3f} K; "
            f"5yr+ {r['mean_effect_5yr_plus_k']:+.3f} ± {r['se_5yr_plus_k']:.3f} K; n={r['n_sites']}"
        )
    sensitivity = rep.get("pooled_block_sensitivity", {})
    for grid in sensitivity.get("grids", []):
        for metric in ("overall", "five_year_plus"):
            result = grid[metric]
            lines.append(f"source-block jackknife {grid['block_size_m']}m offset={grid['origin_offset_fraction']} "
                         f"{metric}: {result}")
    lines.append("Surface temperature is not felt temperature. Pooled intervals are conditional sensitivity diagnostics.")
    return "\n".join(lines)
