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
    need = max(1, int(np.ceil(cfg.min_control_frac_per_scene * k)))
    with np.errstate(invalid="ignore", divide="ignore"):
        ctrl_b = np.where(cnt >= need, np.nansum(Yb, axis=1) / cnt, np.nan)   # B x scenes
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
    treated_ids: pd.Index | None = None,
) -> np.ndarray:
    """DiD effects for n_placebo unplanted cells given fake treatment years.

    Placebo cells are sampled so their land-cover mix matches the treated cells' (the control
    pool is heavier in parks and barren land, which run noisier than streets); otherwise the
    null distribution would be wider than the one the real sites face.
    """
    pool = pd.Index(control_ids).intersection(wide.index)
    if len(pool) < cfg.n_controls + 1 or len(treatment_years) == 0:
        return np.array([])
    n = min(cfg.n_placebo, len(pool))
    weights = None
    feats = features.set_index("site_id") if "site_id" in features.columns else features
    col = cfg.exact_match_col
    if treated_ids is not None and col and col in feats.columns:
        t_cls = feats.loc[pd.Index(treated_ids).intersection(feats.index), col].value_counts(normalize=True)
        pool_cls = feats.reindex(pool)[col]
        n_in_cls = pool_cls.map(pool_cls.value_counts())
        w = pool_cls.map(t_cls).fillna(0.0) / n_in_cls.replace(0, np.nan)
        w = w.fillna(0.0).to_numpy(dtype=float)
        if (w > 0).sum() >= n:
            weights = w / w.sum()
    fake_ids = pool[rng.choice(len(pool), size=n, replace=False, p=weights)]
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
