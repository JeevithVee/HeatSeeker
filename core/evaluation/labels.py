"""Quality labels.

detected        the confidence interval excludes zero and the placebo test agrees
not_detectable  no effect found, and the site had the precision to see one of meaningful size
inconclusive    too few scenes or controls, or too noisy to have seen a meaningful effect
"""

import numpy as np

from core.evaluation.config import EvalConfig


def quality_label(
    effect: float, ci_low: float, ci_high: float, placebo_p: float, mde: float,
    n_pre: int, n_post: int, n_controls: int, cfg: EvalConfig,
) -> str:
    if n_pre < cfg.min_pre_scenes or n_post < cfg.min_post_scenes or n_controls < cfg.min_controls:
        return "inconclusive"
    if np.isnan(effect) or np.isnan(ci_low) or np.isnan(ci_high):
        return "inconclusive"
    excludes_zero = ci_low > 0 or ci_high < 0
    placebo_ok = np.isnan(placebo_p) or placebo_p < cfg.alpha
    if excludes_zero and placebo_ok:
        return "detected"
    if not np.isnan(mde) and mde <= cfg.min_meaningful_effect_k:
        return "not_detectable"
    return "inconclusive"
