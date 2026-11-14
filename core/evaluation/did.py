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


def scene_differences(y_t: np.ndarray, Y_c: np.ndarray) -> np.ndarray:
    """Treated minus mean of controls per scene; NaN where either side is missing."""
    with np.errstate(invalid="ignore"):
        ctrl = np.nanmean(Y_c, axis=0) if Y_c.shape[0] else np.full(y_t.shape, np.nan)
    return y_t - ctrl


def site_did(y_t: np.ndarray, Y_c: np.ndarray, scene_year: np.ndarray, ty: int, cfg: EvalConfig) -> SiteEstimate:
    diff = scene_differences(y_t, Y_c)
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
