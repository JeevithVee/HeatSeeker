"""Difference-in-differences and event study for one site against its matched controls.

Per scene: d_s = treated rel_k - mean(control rel_k). Effect = mean(d_s | post) - mean(d_s | pre).
Scene-level differencing means the city-wide scene effect cancels exactly.
"""

from dataclasses import dataclass

import numpy as np

from core.evaluation.config import EvalConfig


@dataclass
class SiteEstimate:
    effect_k: float
    n_pre: int
    n_post: int
    event_study: dict[int, float]     # years since planting -> effect (K)
    pre_mask: np.ndarray
    post_mask: np.ndarray
    diff: np.ndarray                  # per-scene treated-minus-controls difference


def scene_differences(y_t: np.ndarray, Y_c: np.ndarray, min_control_frac: float = 0.0) -> np.ndarray:
    """Treated minus mean of controls per scene; NaN where either side is missing or too few
    controls are present in the scene (partial-coverage edge scenes)."""
    k = Y_c.shape[0]
    if k == 0:
        return np.full(y_t.shape, np.nan)
    present = (~np.isnan(Y_c)).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        ctrl = np.where(present > 0, np.nansum(Y_c, axis=0) / present, np.nan)
    need = max(1, int(np.ceil(min_control_frac * k)))
    ctrl = np.where(present >= need, ctrl, np.nan)
    return y_t - ctrl


def site_did(y_t: np.ndarray, Y_c: np.ndarray, scene_year: np.ndarray, ty: int, cfg: EvalConfig) -> SiteEstimate:
    diff = scene_differences(y_t, Y_c, cfg.min_control_frac_per_scene)
    valid = ~np.isnan(diff)
    pre = valid & (scene_year < ty)
    post = valid & (scene_year >= ty + cfg.post_start_offset)
    n_pre, n_post = int(pre.sum()), int(post.sum())

    pre_mean = diff[pre].mean() if n_pre else np.nan
    post_mean = diff[post].mean() if n_post else np.nan
    effect = float(post_mean - pre_mean) if n_pre and n_post else float("nan")

    es: dict[int, float] = {}
    if n_pre:
        rel_years = scene_year - ty
        for ys in np.unique(rel_years[valid]):
            m = valid & (rel_years == ys)
            es[int(ys)] = float(diff[m].mean() - pre_mean)
    return SiteEstimate(effect, n_pre, n_post, es, pre, post, diff)
