"""Conditional spatial/source-block jackknife sensitivity for pooled effects.

A block deletion removes complete trajectories of BOTH treated and control cells.
A reused control is removed from every affected matched set together. Matches stay
fixed (no rematching); scene coverage/support checks are applied in every deletion.
The normal intervals are sensitivity diagnostics, not causal confidence intervals:
dependence across blocks, match selection and observational bias remain possible.
"""

from collections import Counter

import numpy as np
import pandas as pd


def control_reuse(matches):
    uses = Counter(c for controls in matches.values() for c in controls)
    return {
        "unique_matched_controls": len(uses),
        "total_control_assignments": sum(uses.values()),
        "controls_reused_by_multiple_sites": sum(n > 1 for n in uses.values()),
        "max_treated_sites_per_control": max(uses.values(), default=0),
    }


def _mean_rows(values, mask):
    count = mask.sum(axis=1)
    return np.divide(np.where(mask, values, 0).sum(axis=1), count,
                     out=np.full(len(values), np.nan), where=count > 0)


def _summarize_deletions(point, deleted, retained, n_sites, min_blocks, min_retained):
    deleted = np.asarray(deleted, dtype=float)
    result = {"mean_effect_k": point, "n_sites": n_sites, "n_blocks": len(deleted),
              "min_retained_fraction": min(retained, default=0.0)}
    if (n_sites < 2 or len(deleted) < min_blocks or not np.isfinite(deleted).all()
            or result["min_retained_fraction"] < min_retained):
        return {**result, "status": "insufficient_block_support", "se_k": None,
                "normal_interval_low_k": None, "normal_interval_high_k": None}
    n = len(deleted)
    se = float(np.sqrt((n - 1) / n * np.sum((deleted - deleted.mean()) ** 2)))
    return {**result, "status": "sensitivity_only", "se_k": se,
            "normal_interval_low_k": point - 1.96 * se, "normal_interval_high_k": point + 1.96 * se}


def pooled_block_sensitivity(wide, scene_year, gold, matches, features, cfg,
                             block_sizes_m=(2000, 5000), offsets=(0.0, 0.5),
                             min_blocks=10, min_retained=0.8):
    """Delete equal-area geographic blocks at prespecified sizes and shifted origins.

    Primary pooled set requires minimum pre/post scenes and controls. Five-year-plus
    effects first average event-year means within each site, then average sites.
    An unsupported deletion invalidates that grid's interval rather than being dropped.
    Coordinates are supplied as table columns; no country-specific dependencies.
    """
    note = ("Conditional on fixed matches and observed scenes. Deletes treated and control trajectories "
            "jointly; preserves reused-control dependence within each deletion. Spatial blocks at "
            "2 km and 5 km with two origins are sensitivity choices, not validated independence "
            "boundaries. Intervals are normal approximations, not causal confidence intervals.")
    out = {"method": "joint_source_block_delete_one_jackknife", "limitations": note,
           "control_reuse": control_reuse(matches), "grids": []}
    if gold.empty:
        return {**out, "status": "no_treated_sites"}
    feats = features.set_index("site_id") if "site_id" in features else features
    ids = [s for s in gold.site_id if s in matches and len(matches[s]) >= cfg.min_controls]
    if not ids:
        return {**out, "status": "insufficient_controls"}
    support = pd.Index(sorted(set(ids).union(c for s in ids for c in matches[s])))
    if not {"centroid_lat", "centroid_lon"}.issubset(feats.columns):
        return {**out, "status": "coordinates_unavailable"}
    coordinates = feats.reindex(support)[["centroid_lat", "centroid_lon"]]
    if not np.isfinite(coordinates.to_numpy(dtype=float)).all():
        return {**out, "status": "coordinates_unavailable"}

    index = {s: i for i, s in enumerate(wide.index)}
    Y = wide.to_numpy(dtype=float)
    treated_values = Y[[index[s] for s in ids]]
    k = max(len(matches[s]) for s in ids)
    ctrl_values = np.full((len(ids), k, Y.shape[1]), np.nan)
    ctrl_ids = np.full((len(ids), k), -1, dtype=int)
    support_index = {s: i for i, s in enumerate(support)}
    for i, sid in enumerate(ids):
        controls = matches[sid]
        ctrl_values[i, :len(controls)] = Y[[index[c] for c in controls]]
        ctrl_ids[i, :len(controls)] = [support_index[c] for c in controls]
    assigned = ctrl_ids >= 0
    ctrl_finite = np.isfinite(ctrl_values)
    ctrl_zero = np.nan_to_num(ctrl_values, nan=0.0)
    years = gold.set_index("site_id").loc[ids, "treatment_year"].to_numpy(dtype=int)
    rel_year = scene_year[None, :] - years[:, None]

    def estimate(keep_treated, keep_controls):
        count = (ctrl_finite & keep_controls[:, :, None]).sum(axis=1)
        total = (ctrl_zero * keep_controls[:, :, None]).sum(axis=1)
        n_controls = keep_controls.sum(axis=1)
        need = np.maximum(1, np.ceil(cfg.min_control_frac_per_scene * n_controls)).astype(int)
        mean = np.divide(total, count, out=np.full_like(total, np.nan), where=count >= need[:, None])
        diff = treated_values - mean
        finite = np.isfinite(diff)
        pre = finite & (rel_year < 0)
        post = finite & (rel_year >= cfg.post_start_offset)
        pre_mean = _mean_rows(diff, pre)
        effect = _mean_rows(diff, post) - pre_mean
        valid = (keep_treated & (n_controls >= cfg.min_controls)
                 & (pre.sum(axis=1) >= cfg.min_pre_scenes) & (post.sum(axis=1) >= cfg.min_post_scenes))
        late_years = []
        for year in np.unique(rel_year[rel_year >= 5]):
            late_years.append(_mean_rows(diff, finite & (rel_year == year)) - pre_mean)
        late = np.full(len(ids), np.nan)
        if late_years:
            late_matrix = np.column_stack(late_years)
            late = _mean_rows(late_matrix, np.isfinite(late_matrix))
        return {"overall": (effect, valid & np.isfinite(effect)),
                "five_year_plus": (late, valid & np.isfinite(late))}

    baseline = estimate(np.ones(len(ids), dtype=bool), assigned)
    out["n_sites_with_minimum_support"] = int(baseline["overall"][1].sum())
    lat = coordinates.centroid_lat.to_numpy(dtype=float)
    lon = coordinates.centroid_lon.to_numpy(dtype=float)
    # Local equirectangular coordinates in metres, adequate for these city-sized grids.
    x = (lon - lon.min()) * np.cos(np.deg2rad(lat.mean())) * 111_195
    y = (lat - lat.min()) * 111_195
    treated_positions = np.array([support_index[s] for s in ids])
    for size in block_sizes_m:
        for offset in offsets:
            cells = np.column_stack((np.floor(x / size + offset), np.floor(y / size + offset))).astype(int)
            _, blocks = np.unique(cells, axis=0, return_inverse=True)
            ctrl_blocks = np.full_like(ctrl_ids, -1)
            ctrl_blocks[assigned] = blocks[ctrl_ids[assigned]]
            deletes, retained = {m: [] for m in baseline}, {m: [] for m in baseline}
            for block in np.unique(blocks):
                estimates = estimate(blocks[treated_positions] != block, assigned & (ctrl_blocks != block))
                for metric, (values, valid) in estimates.items():
                    base_valid = baseline[metric][1]
                    selected = valid & base_valid
                    deletes[metric].append(float(values[selected].mean()) if selected.any() else np.nan)
                    retained[metric].append(float(selected.sum() / max(base_valid.sum(), 1)))
            grid = {"block_size_m": size, "origin_offset_fraction": offset}
            for metric, (values, valid) in baseline.items():
                point = float(values[valid].mean()) if valid.any() else None
                grid[metric] = _summarize_deletions(point, deletes[metric], retained[metric], int(valid.sum()),
                                                  min_blocks, min_retained)
            out["grids"].append(grid)
    return {**out, "status": "sensitivity_only"}
