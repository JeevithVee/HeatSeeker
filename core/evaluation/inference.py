"""Uncertainty: bootstrap over scenes and controls; placebo tests with fake planting years.

Bootstrap: resample pre scenes, post scenes and the control set with replacement, B times,
and recompute the DiD. Placebo: give unplanted cells a fake treatment year drawn from the
real treatment years, match and estimate them exactly like real sites; the spread of those
estimates is what "no effect" looks like in this city.
"""

import numpy as np
import pandas as pd

from core.evaluation.config import EvalConfig
from core.evaluation.did import site_did
from core.evaluation.matching import match_controls


def bootstrap_effect(
    y_t: np.ndarray, Y_c: np.ndarray, pre: np.ndarray, post: np.ndarray, rng: np.random.Generator, cfg: EvalConfig
) -> tuple[float, float, float]:
    """Return (se, ci_low, ci_high) from B bootstrap replicates of the DiD effect."""
    pre_idx = np.flatnonzero(pre)
    post_idx = np.flatnonzero(post)
    k = Y_c.shape[0]
    if len(pre_idx) == 0 or len(post_idx) == 0 or k == 0:
        return float("nan"), float("nan"), float("nan")
    B = cfg.n_bootstrap

    c_draw = rng.integers(0, k, size=(B, k))                      # B x k control resamples
    Yb = Y_c[c_draw]                                              # B x k x scenes
    cnt = (~np.isnan(Yb)).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        ctrl_b = np.where(cnt > 0, np.nansum(Yb, axis=1) / cnt, np.nan)   # B x scenes
    diff_b = y_t[None, :] - ctrl_b                                # B x scenes

    pre_draw = pre_idx[rng.integers(0, len(pre_idx), size=(B, len(pre_idx)))]
    post_draw = post_idx[rng.integers(0, len(post_idx), size=(B, len(post_idx)))]
    rows = np.arange(B)[:, None]
    with np.errstate(invalid="ignore"):
        eff = np.nanmean(diff_b[rows, post_draw], axis=1) - np.nanmean(diff_b[rows, pre_draw], axis=1)
    eff = eff[~np.isnan(eff)]
    if len(eff) < 10:
        return float("nan"), float("nan"), float("nan")
    lo, hi = np.quantile(eff, [cfg.alpha / 2, 1 - cfg.alpha / 2])
    return float(eff.std(ddof=1)), float(lo), float(hi)


def placebo_distribution(
    control_ids: pd.Index,
    treatment_years: np.ndarray,
    features: pd.DataFrame,
    yearly: pd.DataFrame,
    wide: pd.DataFrame,
    scene_year: np.ndarray,
    rng: np.random.Generator,
    cfg: EvalConfig,
) -> np.ndarray:
    """DiD effects for n_placebo unplanted cells given fake treatment years."""
    pool = pd.Index(control_ids).intersection(wide.index)
    if len(pool) < cfg.n_controls + 1 or len(treatment_years) == 0:
        return np.array([])
    n = min(cfg.n_placebo, len(pool))
    fake_ids = pool[rng.choice(len(pool), size=n, replace=False)]
    fake = pd.DataFrame({
        "site_id": fake_ids,
        "treatment_year": rng.choice(treatment_years, size=n, replace=True),
    })
    W = wide.to_numpy(dtype=float)
    row = {sid: i for i, sid in enumerate(wide.index)}
    out = []
    for ty, grp in fake.groupby("treatment_year"):
        others = pool.difference(grp["site_id"])
        m = match_controls(grp, others, features, yearly, cfg)
        for sid, ctrls in m.items():
            est = site_did(W[row[sid]], W[[row[c] for c in ctrls]], scene_year, int(ty), cfg)
            if est.n_pre >= cfg.min_pre_scenes and est.n_post >= cfg.min_post_scenes and not np.isnan(est.effect_k):
                out.append(est.effect_k)
    return np.asarray(out)


def placebo_p_value(effect: float, placebo: np.ndarray) -> float:
    """Share of placebo effects at least as large in magnitude (with +1 smoothing)."""
    if np.isnan(effect) or len(placebo) == 0:
        return float("nan")
    return float((np.sum(np.abs(placebo) >= abs(effect)) + 1) / (len(placebo) + 1))
