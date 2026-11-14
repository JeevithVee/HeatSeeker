"""Turn silver.interventions into a treatment table and a control pool.

A cell is "planted" in the first year it received at least min_dose trees. Cells with at most
control_max_trees trees over the whole record are the control pool. Everything in between
(lightly planted) is excluded from both sides.
"""

import pandas as pd

from core.evaluation.config import EvalConfig


def treatment_table(
    interventions: pd.DataFrame,
    all_site_ids: pd.Index,
    cfg: EvalConfig,
    variant: str = "all",
) -> tuple[pd.DataFrame, pd.Index]:
    """Return (treated, control_ids).

    treated columns: site_id, treatment_year, dose_trees, batch_frac, intervention_type.
    variant 'excl_batch_dated' drops treated cells whose batch-dated share exceeds the threshold.
    """
    iv = interventions.copy()
    for col in ("trees_batch_dated", "trees_surviving"):
        if col not in iv.columns:
            iv[col] = 0
    iv["trees_batch_dated"] = iv["trees_batch_dated"].fillna(0)

    per_cell = iv.groupby("site_id").agg(
        dose_trees=("trees_planted", "sum"),
        batch_trees=("trees_batch_dated", "sum"),
    )
    per_cell["batch_frac"] = (per_cell["batch_trees"] / per_cell["dose_trees"].clip(lower=1)).fillna(0)

    qualifying = iv.loc[iv["trees_planted"] >= cfg.min_dose]
    first_year = qualifying.groupby("site_id")["plant_year"].min().rename("treatment_year")
    treated = per_cell.join(first_year, how="inner").reset_index()
    treated["intervention_type"] = cfg.intervention_type
    treated = treated.loc[treated["site_id"].isin(all_site_ids)]

    if variant == "excl_batch_dated":
        treated = treated.loc[treated["batch_frac"] <= cfg.batch_frac_threshold]
    elif variant != "all":
        raise ValueError(f"unknown variant {variant!r}")

    planted_any = per_cell.index[per_cell["dose_trees"] > cfg.control_max_trees]
    control_ids = all_site_ids.difference(planted_any)

    cols = ["site_id", "treatment_year", "dose_trees", "batch_frac", "intervention_type"]
    return treated[cols].reset_index(drop=True), control_ids
