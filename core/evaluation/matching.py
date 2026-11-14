"""Matched controls: for each treated cell, the k nearest unplanted cells.

Distance is standardized Euclidean over static features (canopy, impervious fraction,
elevation) plus the cell's pre-period relative temperature level and trend, with an exact
match on land-cover class when enough candidates exist.
"""

import numpy as np
import pandas as pd

from core.evaluation.config import EvalConfig


def _pre_level_and_slope(ym: pd.DataFrame, pre_years: list[int]) -> pd.DataFrame:
    """Per-cell mean and per-year slope of rel_k over the given pre years (NaN-tolerant)."""
    Y = ym.loc[:, pre_years].to_numpy(dtype=float)
    x = np.array(pre_years, dtype=float)
    mask = ~np.isnan(Y)
    n = mask.sum(axis=1)
    Yz = np.where(mask, Y, 0.0)
    xb = np.where(mask, x, 0.0)
    sum_x = xb.sum(axis=1)
    sum_y = Yz.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_x = sum_x / n
        mean_y = sum_y / n
        sxy = (np.where(mask, (x - mean_x[:, None]) * (Y - mean_y[:, None]), 0.0)).sum(axis=1)
        sxx = (np.where(mask, (x - mean_x[:, None]) ** 2, 0.0)).sum(axis=1)
        slope = np.where(n >= 2, sxy / sxx, 0.0)
    out = pd.DataFrame({"pre_level": mean_y, "pre_slope": slope}, index=ym.index)
    return out


def match_controls(
    treated: pd.DataFrame,
    control_ids: pd.Index,
    features: pd.DataFrame,
    yearly: pd.DataFrame,
    cfg: EvalConfig,
) -> dict[str, list[str]]:
    """Return {treated site_id: [control site_ids]}.

    `yearly` is the cells x years matrix of rel_k from panel.yearly_means.
    """
    feats = features.set_index("site_id") if "site_id" in features.columns else features
    match_vars = [v for v in cfg.match_vars if v in feats.columns]
    scale = feats[match_vars].std(ddof=0).replace(0, 1.0)
    Z_static = (feats[match_vars] - feats[match_vars].mean()) / scale

    matches: dict[str, list[str]] = {}
    years_available = sorted(int(y) for y in yearly.columns)
    control_ids = pd.Index(control_ids).intersection(yearly.index).intersection(feats.index)

    for ty, group in treated.groupby("treatment_year"):
        pre_years = [y for y in years_available if y < ty]
        t_ids = pd.Index(group["site_id"]).intersection(yearly.index).intersection(feats.index)
        if len(t_ids) == 0 or len(control_ids) == 0:
            continue

        if len(pre_years) >= 2:
            pre = _pre_level_and_slope(yearly, pre_years)
            pre_scale = pre.std(ddof=0).replace(0, 1.0)
            Z_pre = (pre - pre.mean()) / pre_scale * cfg.pretrend_weight
            Z = pd.concat([Z_static, Z_pre], axis=1)
        else:
            Z = Z_static
        Z = Z.fillna(0.0)

        Zc_all = Z.loc[control_ids].to_numpy(dtype=float)
        classes_c = feats.loc[control_ids, cfg.exact_match_col].to_numpy() if cfg.exact_match_col else None

        for sid in t_ids:
            zt = Z.loc[sid].to_numpy(dtype=float)
            cand = np.arange(len(control_ids))
            if classes_c is not None:
                same = np.flatnonzero(classes_c == feats.at[sid, cfg.exact_match_col])
                if len(same) >= cfg.n_controls:
                    cand = same
            d = np.sqrt(((Zc_all[cand] - zt) ** 2).sum(axis=1))
            k = min(cfg.n_controls, len(cand))
            best = cand[np.argpartition(d, k - 1)[:k]]
            matches[sid] = list(control_ids[best])
    return matches
