"""Turn silver.interventions into a treatment table and a control pool.

A cell is "planted" in the first year its cumulative count (from the start of the treatment
window) reaches min_dose trees; NYC plants a median of 5 trees per cell per year, so a
single-year bar would miss steady planters. Only cells reaching min_dose inside the window are
evaluated. Cells with at most control_max_trees trees over the WHOLE record (all years, so
late-planted cells are excluded) are the control pool. Everything in between is excluded.
"""

import pandas as pd

from core.evaluation.config import EvalConfig


def eligible_cells(features: pd.DataFrame, cfg: EvalConfig) -> pd.Index:
    """Cells allowed into the analysis at all: drop water/wetland-dominated cells."""
    f = features.set_index("site_id") if "site_id" in features.columns else features
    if cfg.exclude_land_cover and "land_cover_class" in f.columns:
        f = f.loc[~f["land_cover_class"].isin(cfg.exclude_land_cover)]
    return pd.Index(f.index)


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
    all_site_ids = pd.Index(all_site_ids)
    iv = interventions.copy()
    for col in ("trees_batch_dated", "trees_surviving"):
        if col not in iv.columns:
            iv[col] = 0
    iv["trees_batch_dated"] = iv["trees_batch_dated"].fillna(0)

    lo, hi = cfg.treatment_window
    in_window = iv.loc[iv["plant_year"].between(lo, hi)]
    per_cell = in_window.groupby("site_id").agg(
        dose_trees=("trees_planted", "sum"),
        batch_trees=("trees_batch_dated", "sum"),
    )
    per_cell["batch_frac"] = (per_cell["batch_trees"] / per_cell["dose_trees"].clip(lower=1)).fillna(0)

    # treatment_year = first year the cumulative count (from the window start) reaches min_dose
    yearly = in_window.groupby(["site_id", "plant_year"])["trees_planted"].sum().unstack(fill_value=0)
    yearly = yearly.reindex(columns=range(lo, hi + 1), fill_value=0)
    cum = yearly.cumsum(axis=1)
    reached = cum.ge(cfg.min_dose)
    first_year = reached.idxmax(axis=1).where(reached.any(axis=1)).dropna().astype(int).rename("treatment_year")
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
