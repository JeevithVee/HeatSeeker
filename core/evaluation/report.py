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


def build_report(
    gold: pd.DataFrame,
    filtered_panel: pd.DataFrame,
    treated_ids: pd.Index,
    matches: dict[str, list[str]],
    features: pd.DataFrame,
    placebo: np.ndarray,
    cfg: EvalConfig,
) -> dict:
    scenes = filtered_panel.drop_duplicates("scene_id")
    scenes_per_year = scenes.groupby("scene_year").size().to_dict()
    es = pooled_event_study(gold)
    pre = es.loc[es["years_since"] < 0]
    pre_mean = float(np.average(pre["mean_effect_k"], weights=pre["n_sites"])) if len(pre) else float("nan")
    balance = standardized_mean_differences(treated_ids, matches, features, cfg)
    return {
        "n_scenes": int(len(scenes)),
        "scenes_per_year": {int(k): int(v) for k, v in scenes_per_year.items()},
        "n_cells_in_panel": int(filtered_panel["site_id"].nunique()),
        "n_treated": int(len(treated_ids)),
        "n_matched": int(sum(1 for s in treated_ids if s in matches)),
        "labels": gold["quality_label"].value_counts().to_dict(),
        "median_mde_k": float(gold["mde_k"].median()) if len(gold) else float("nan"),
        "median_effect_k_detected": float(gold.loc[gold["quality_label"] == "detected", "effect_k"].median())
        if (gold["quality_label"] == "detected").any() else float("nan"),
        "pre_period_mean_effect_k": pre_mean,                 # should be ~0
        "max_abs_smd": float(balance["smd"].abs().max()) if len(balance) else float("nan"),   # < 0.1 good, < 0.25 ok
        "balance": balance.round(4).to_dict("records"),
        "placebo_mean_k": float(np.mean(placebo)) if len(placebo) else float("nan"),
        "placebo_sd_k": float(np.std(placebo, ddof=1)) if len(placebo) > 1 else float("nan"),
        "placebo_q95_abs_k": float(np.quantile(np.abs(placebo), 0.95)) if len(placebo) else float("nan"),
        "event_study": es.round(4).to_dict("records"),
    }


def format_report(rep: dict) -> str:
    lines = [
        f"scenes kept: {rep['n_scenes']} over {len(rep['scenes_per_year'])} years; cells: {rep['n_cells_in_panel']:,}",
        f"treated: {rep['n_treated']:,} (matched {rep['n_matched']:,}); labels: {rep['labels']}",
        f"median MDE {rep['median_mde_k']:.2f} K; median detected effect {rep['median_effect_k_detected']:.2f} K",
        f"pre-period pooled effect {rep['pre_period_mean_effect_k']:+.3f} K (want ~0)",
        f"control balance: max |SMD| {rep['max_abs_smd']:.3f} (want < 0.1)",
        f"placebo: mean {rep['placebo_mean_k']:+.3f} K, sd {rep['placebo_sd_k']:.3f} K, 95% |q| {rep['placebo_q95_abs_k']:.3f} K",
        "event study (years since planting: mean K, n): "
        + ", ".join(f"{r['years_since']}: {r['mean_effect_k']:+.2f} ({r['n_sites']})" for r in rep["event_study"]),
    ]
    return "\n".join(lines)
