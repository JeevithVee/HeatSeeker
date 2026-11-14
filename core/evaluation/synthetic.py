"""A synthetic city with a known, built-in cooling effect.

Used by the permanent recovery test and for building downstream code before real tables
exist. Produces silver.panel, silver.features and silver.interventions in the frozen schemas,
plus a truth table with each planted cell's true long-run effect.

Design, chosen to stress the engine the way real data will:
  * cell fixed effects driven by impervious and canopy fraction (hot roofs, cool parks)
  * a city-wide scene effect per date, so absolute LST is meaningless without differencing
  * trees planted 2015-2019; cooling ramps in over 5 years, scaled by dose
  * a set of planted cells with zero true effect (to test "not detectable")
  * batch-dated cells whose "planting" is a data-entry artifact with zero effect
  * winter, cloudy, low-valid-pixel and non-Landsat rows that must be filtered out
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SyntheticSpec:
    n_cells: int = 3000
    years: tuple = (2013, 2024)
    scenes_per_summer: int = 6
    n_treated: int = 240
    n_null_treated: int = 60          # planted, but no true effect
    n_batch_dated: int = 50           # "planted" by batch entry, no true effect
    beta_k: float = 1.5               # long-run cooling (K) for a dose of dose_ref trees
    dose_ref: float = 40.0
    ramp_years: float = 5.0
    noise_k: float = 1.0
    seed: int = 42


def make_city(spec: SyntheticSpec = SyntheticSpec()) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(spec.seed)
    n = spec.n_cells
    site_id = np.array([f"syn{i:06d}" for i in range(n)])

    # --- features ---
    impervious = np.clip(rng.beta(2, 2, n), 0, 1)
    canopy = np.clip(rng.beta(2, 5, n) * (1 - 0.6 * impervious), 0, 1)
    elevation = rng.gamma(3, 10, n)
    lc = np.select(
        [impervious > 0.8, impervious > 0.6, impervious > 0.35, canopy > 0.4],
        ["developed_high", "developed_medium", "developed_low", "forest"], default="developed_open",
    )
    population = rng.gamma(2, 400, n)
    vuln = rng.uniform(0, 1, n)
    features = pd.DataFrame({
        "country_code": "US", "city_id": "syn", "site_id": site_id,
        "centroid_lat": 40.5 + rng.random(n) * 0.4, "centroid_lon": -74.2 + rng.random(n) * 0.5, "area_km2": 0.105,
        "canopy_frac_baseline": canopy, "canopy_year_baseline": 2014,
        "canopy_frac_latest": np.clip(canopy + rng.normal(0.01, 0.02, n), 0, 1), "canopy_year_latest": 2023,
        "impervious_frac": impervious, "land_cover_class": lc, "land_cover_year": 2016,
        "elevation_m": elevation, "population": population, "vulnerable_residents": population * vuln,
        "vulnerability_index": vuln, "median_household_income": rng.gamma(4, 18000, n),
        "existing_tree_count": rng.poisson(40 * canopy + 5, n),
    })
    cell_fe = 8 * impervious - 6 * canopy + 0.01 * (elevation - elevation.mean()) + rng.normal(0, 1.0, n)

    # --- treatment assignment ---
    idx = rng.permutation(n)
    real = idx[: spec.n_treated]
    null = idx[spec.n_treated: spec.n_treated + spec.n_null_treated]
    batch = idx[spec.n_treated + spec.n_null_treated: spec.n_treated + spec.n_null_treated + spec.n_batch_dated]
    planted = np.concatenate([real, null, batch])
    ty = rng.integers(2015, 2020, size=len(planted))
    dose = rng.integers(10, 81, size=len(planted))
    true_long_run = np.zeros(len(planted))
    true_long_run[: len(real)] = -spec.beta_k * dose[: len(real)] / spec.dose_ref

    # lightly planted background cells (1-2 trees) that are still valid controls
    light = rng.choice(np.setdiff1d(np.arange(n), planted), size=n // 5, replace=False)

    def iv_row(c, year, planted_n, batch_n):
        removed = int(rng.integers(0, max(1, planted_n // 10)))
        return {
            "country_code": "US", "city_id": "syn", "site_id": site_id[c], "plant_year": int(year),
            "intervention_type": "tree_planting", "trees_planted": int(planted_n), "trees_removed": removed,
            "trees_surviving": int(planted_n) - removed, "removed_flag": int(planted_n) - removed == 0,
            "removal_tracked": True, "trees_batch_dated": int(batch_n),
            "first_plant_date": pd.Timestamp(f"{year}-04-15").date(),
            "last_plant_date": pd.Timestamp(f"{year}-11-15").date(), "source": "synthetic",
        }

    iv_rows = []
    for j, c in enumerate(planted):
        is_batch = j >= len(real) + len(null)
        iv_rows.append(iv_row(c, ty[j], dose[j], dose[j] if is_batch else 0))
    for c in light:
        iv_rows.append(iv_row(c, rng.integers(2015, 2020), rng.integers(1, 3), 0))
    interventions = pd.DataFrame(iv_rows)

    # --- scenes ---
    scenes = []
    y0, y1 = spec.years
    for year in range(y0, y1 + 1):
        for s in range(spec.scenes_per_summer):
            day = int(rng.integers(0, 92))
            date = pd.Timestamp(f"{year}-06-01", tz="UTC") + pd.Timedelta(days=day, hours=15, minutes=int(rng.integers(0, 50)))
            cloud = float(rng.beta(1, 8))
            scenes.append((date, "LANDSAT_9" if year >= 2022 and s % 2 else "LANDSAT_8", cloud, False))
        # one winter scene and one cloudy summer scene per year, plus a stray non-Landsat row set
        scenes.append((pd.Timestamp(f"{year}-01-20T15:30", tz="UTC"), "LANDSAT_8", 0.05, False))
        scenes.append((pd.Timestamp(f"{year}-07-10T15:30", tz="UTC"), "LANDSAT_8", 0.7, True))
        scenes.append((pd.Timestamp(f"{year}-07-20T20:00", tz="UTC"), "ECOSTRESS", 0.05, False))
    scene_df = pd.DataFrame(scenes, columns=["acquired_at_utc", "sensor", "scene_cloud_cover_frac", "garbage"])
    scene_df["scene_id"] = [f"{r.sensor}_{r.acquired_at_utc.strftime('%Y%m%dT%H%M')}" for r in scene_df.itertuples()]
    scene_df["scene_year"] = scene_df["acquired_at_utc"].dt.year

    # --- panel ---
    effect_by_cell_year = {}
    for j, c in enumerate(planted):
        for year in range(y0, y1 + 1):
            ys = year - ty[j]
            effect_by_cell_year[(c, year)] = true_long_run[j] * min(max(ys, 0) / spec.ramp_years, 1.0) if ys >= 1 else 0.0

    frames = []
    for sc in scene_df.itertuples():
        base = 300 + 12 * rng.random()                                  # city-wide scene effect
        lst = base + cell_fe + rng.normal(0, spec.noise_k, n)
        eff = np.zeros(n)
        for c in planted:
            eff[c] = effect_by_cell_year[(c, sc.scene_year)]
        lst = lst + eff
        valid = np.clip(rng.beta(12, 1, n), 0, 1)
        lowq = rng.random(n) < 0.08
        valid[lowq] = rng.uniform(0.2, 0.69, lowq.sum())
        lst[lowq] += rng.normal(-4, 3, lowq.sum())                       # partially cloudy cells read cold
        if sc.garbage:
            lst += rng.normal(-8, 5, n)
        # Agent 2's final silver.panel columns (MessageBoard, Agent 2 msg 1).
        frames.append(pd.DataFrame({
            "country_code": "US", "city_id": "syn", "site_id": site_id, "scene_id": sc.scene_id,
            "acquired_at_utc": sc.acquired_at_utc, "acquired_date": sc.acquired_at_utc.date(),
            "year": int(sc.scene_year), "sensor": sc.sensor,
            "lst_mean_k": lst + rng.normal(0, 0.1, n), "lst_median_k": lst, "lst_std_k": rng.uniform(0.5, 2, n),
            "valid_pixel_count": np.round(valid * 117).astype(int), "valid_pixel_frac": valid,
            "is_clear": valid >= 0.8, "scene_cloud_cover_frac": sc.scene_cloud_cover_frac,
            "city_clear_frac": float((valid >= 0.8).mean()), "sun_elevation_deg": 60.0 + rng.normal(0, 3),
            "wrs_path": 13 if sc.scene_year % 2 else 14, "wrs_row": 32,
            "tmax_c": float(base - 273.15 + rng.normal(0, 2)), "tmin_c": float(base - 283.15 + rng.normal(0, 2)),
            "wind_speed_ms": float(rng.gamma(2, 1.5)), "precip_mm": 0.0,
            "source": "synthetic", "license": "none",
        }))
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.sample(frac=0.95, random_state=spec.seed).reset_index(drop=True)   # some cells missing per scene

    # Average true effect over the post period (years ty+1..y1): what a DiD on this panel
    # should recover. The long-run value is what the event study reaches after ramp_years.
    true_post_avg = np.array([
        np.mean([effect_by_cell_year[(c, yr)] for yr in range(int(ty[j]) + 1, y1 + 1)]) if ty[j] + 1 <= y1 else 0.0
        for j, c in enumerate(planted)
    ])
    truth = pd.DataFrame({
        "site_id": site_id[planted], "treatment_year": ty, "dose_trees": dose,
        "true_effect_k": true_long_run, "true_post_avg_k": true_post_avg,
        "group": ["real"] * len(real) + ["null"] * len(null) + ["batch"] * len(batch),
    })
    return {"panel": panel, "features": features, "interventions": interventions, "truth": truth}
