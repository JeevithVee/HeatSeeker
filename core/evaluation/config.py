"""Tunable parameters for the evaluation engine. Defaults are for the NYC prototype."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalConfig:
    # --- scene filtering (silver.panel) ---
    lst_col: str = "lst_median_k"            # main temperature measure per cell per scene
    summer_months: tuple = (6, 7, 8)
    sensors: tuple = ("L8", "L9")            # Landsat only; never mixed with ECOSTRESS
    max_scene_cloud_frac: float = 0.3
    min_valid_pixel_frac: float = 0.7
    min_cells_per_scene: int = 200           # drop scenes that cover too little of the city
    tmax_c_range: tuple | None = None        # optional (lo, hi) filter on per-scene tmax_c if present

    # --- treatment definition (silver.interventions) ---
    min_dose: int = 10                       # trees planted in one year for a cell to count as planted
    control_max_trees: int = 2               # cells with at most this many trees ever are controls
    batch_frac_threshold: float = 0.5        # excl_batch_dated variant drops treated cells above this
    intervention_type: str = "tree_planting"

    # --- matching (silver.features) ---
    match_vars: tuple = ("canopy_frac_baseline", "impervious_frac", "elevation_m")
    exact_match_col: str | None = "land_cover_class"
    n_controls: int = 10
    pretrend_weight: float = 1.0             # weight of pre-period level and slope in the distance

    # --- estimation ---
    post_start_offset: int = 1               # first post year = treatment_year + offset (donut on year 0)
    min_pre_scenes: int = 5
    min_post_scenes: int = 5
    min_controls: int = 3
    n_bootstrap: int = 200
    n_placebo: int = 200
    alpha: float = 0.05
    power_z: float = 2.8                     # 1.96 + 0.84: 80% power at alpha 0.05, for the MDE
    # A site is "not_detectable" only if it could have resolved an effect this large (K). With
    # 30 m Landsat and ~1 K per-cell scene noise, per-site MDEs are ~0.8-1.1 K, so 1.0 K is
    # the honest floor; sub-degree effects are "inconclusive" at the single-site level.
    min_meaningful_effect_k: float = 1.0
    seed: int = 0

    # --- identity ---
    required_panel_cols: tuple = field(default=(
        "country_code", "city_id", "site_id", "scene_id", "acquired_at_utc", "sensor",
        "valid_pixel_frac", "scene_cloud_cover_frac",
    ))
