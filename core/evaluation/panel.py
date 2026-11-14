"""Scene filtering and relative temperature.

Every cell is measured relative to its own scene's city-wide median, so day-to-day weather
and the satellite's calibration drift cancel. Only clear-sky summer Landsat scenes are kept.
"""

import numpy as np
import pandas as pd

from core.evaluation.config import EvalConfig


def filter_scenes(panel: pd.DataFrame, cfg: EvalConfig) -> pd.DataFrame:
    """Keep clear-sky summer Landsat rows with enough valid pixels. Adds scene_year."""
    missing = [c for c in cfg.required_panel_cols + (cfg.lst_col,) if c not in panel.columns]
    if missing:
        raise ValueError(f"silver.panel is missing columns: {missing}")

    p = panel.copy()
    t = pd.to_datetime(p["acquired_at_utc"], utc=True)
    p["scene_year"] = t.dt.year.astype(int)
    month = t.dt.month

    keep = (
        month.isin(cfg.summer_months)
        & p["sensor"].isin(cfg.sensors)
        & (p["scene_cloud_cover_frac"] <= cfg.max_scene_cloud_frac)
        & (p["valid_pixel_frac"] >= cfg.min_valid_pixel_frac)
        & p[cfg.lst_col].notna()
    )
    if cfg.tmax_c_range is not None and "tmax_c" in p.columns:
        lo, hi = cfg.tmax_c_range
        keep &= p["tmax_c"].between(lo, hi) | p["tmax_c"].isna()
    p = p.loc[keep]

    cells_per_scene = p.groupby("scene_id")["site_id"].transform("size")
    p = p.loc[cells_per_scene >= cfg.min_cells_per_scene]
    return p.reset_index(drop=True)


def relative_temperature(panel: pd.DataFrame, cfg: EvalConfig) -> pd.DataFrame:
    """Add rel_k: cell LST minus the scene's city-wide median LST (Kelvin)."""
    p = panel.copy()
    p["rel_k"] = p[cfg.lst_col] - p.groupby("scene_id")[cfg.lst_col].transform("median")
    return p


def to_wide(panel: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Pivot to cells x scenes matrix of rel_k (NaN where a cell is missing from a scene).

    Returns (wide, scene_year) with scene columns sorted by acquisition time.
    """
    scene_meta = (
        panel.groupby("scene_id")
        .agg(acquired_at_utc=("acquired_at_utc", "first"), scene_year=("scene_year", "first"))
        .sort_values("acquired_at_utc")
    )
    wide = panel.pivot(index="site_id", columns="scene_id", values="rel_k")
    wide = wide.reindex(columns=scene_meta.index)
    return wide, scene_meta["scene_year"].to_numpy()


def yearly_means(wide: pd.DataFrame, scene_year: np.ndarray) -> pd.DataFrame:
    """Mean rel_k per cell per year (cells x years)."""
    years = np.unique(scene_year)
    out = {}
    for y in years:
        out[int(y)] = wide.loc[:, scene_year == y].mean(axis=1)
    return pd.DataFrame(out, index=wide.index)
