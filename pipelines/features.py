"""City grid + rasters + census -> silver.features (one row per cell).

City-agnostic: inputs arrive as plain arrays and frames, so the same code
serves any country whose adapters produce them.
"""
import h3
import numpy as np
import pandas as pd

import schema

RASTER_NODATA_ABOVE = 100   # percent layers: anything above 100 is a fill value


def pixel_site_ids(lon, lat, resolution=schema.H3_RESOLUTION):
    """H3 cell of every pixel centre. The slow step; compute once per raster grid."""
    return np.array([h3.latlng_to_cell(la, lo, resolution) for lo, la in zip(lon, lat)])


def zonal_mean_fraction(site_ids, values):
    """Mean of a 0-100 percent raster per cell, as a 0-1 fraction.

    Fill values are ignored. Returns a Series indexed by site_id.
    """
    values = np.asarray(values).ravel()
    ok = values <= RASTER_NODATA_ABOVE
    return pd.Series(values[ok], dtype="float64").groupby(site_ids[ok]).mean() / 100.0


def zonal_dominant_class(site_ids, values, class_names, nodata_above=RASTER_NODATA_ABOVE):
    """Most common class per cell. Returns a Series of class names by site_id."""
    values = np.asarray(values).ravel()
    ok = values <= nodata_above
    counts = (pd.DataFrame({"site_id": site_ids[ok], "cls": values[ok]})
              .value_counts().rename("n").reset_index()
              .sort_values(["site_id", "n", "cls"], ascending=[True, False, True]))
    top = counts.drop_duplicates("site_id").set_index("site_id")["cls"]
    return top.map(lambda c: class_names.get(int(c), f"class_{int(c)}"))


def population_by_cell(block_population, resolution=schema.H3_RESOLUTION):
    """Residents per cell from small census units, each assigned to the cell
    holding its internal point. Shares are population-weighted.

    Returns a frame indexed by site_id: population, share_age_65_plus,
    share_low_income.
    """
    df = block_population.copy()
    df["site_id"] = [h3.latlng_to_cell(la, lo, resolution) for la, lo in zip(df["lat"], df["lon"])]
    out = df.groupby("site_id").agg(population=("population", "sum"))
    for share in ("share_age_65_plus", "share_low_income"):
        known = df[df[share].notna()]
        weighted = (known[share] * known["population"]).groupby(known["site_id"]).sum()
        weight = known.groupby("site_id")["population"].sum()
        out[share] = (weighted / weight.where(weight > 0)).reindex(out.index)
    return out


DEFAULT_VULNERABILITY_WEIGHTS = {"share_age_65_plus": 0.5, "share_low_income": 0.5}


def weighted_vulnerability(weights=None):
    """Formula builder: weighted mean of raw shares, each min-max scaled
    within the city. `weights` comes from the country config
    (vulnerability_formula.weights); equal weights when absent."""
    weights = weights or DEFAULT_VULNERABILITY_WEIGHTS
    total = sum(weights.values())

    def formula(features):
        index = 0.0
        for column, weight in weights.items():
            s = features[column]
            span = s.max() - s.min()
            index = index + (weight / total) * ((s - s.min()) / span if span > 0 else s * 0.0)
        return index
    return formula


default_vulnerability = weighted_vulnerability()


def build_features(grid, *, canopy_baseline=None, canopy_latest=None, impervious=None,
                   land_cover=None, canopy_year_baseline=None, canopy_year_latest=None,
                   land_cover_year=None, population=None, elevation=None,
                   existing_trees=None, vulnerability_fn=default_vulnerability):
    """Assemble silver.features for one city.

    grid               frame from pipelines.grid (one row per cell)
    canopy_*, impervious, land_cover, elevation, existing_trees
                       Series indexed by site_id, or None when not yet available
    population         frame from population_by_cell, or None
    vulnerability_fn   formula from the country config; takes the features
                       frame, returns a 0-1 Series
    """
    out = grid.set_index("site_id").copy()

    def col(series):
        return series.reindex(out.index) if series is not None else np.nan

    out["canopy_frac_baseline"] = col(canopy_baseline)
    out["canopy_year_baseline"] = canopy_year_baseline if canopy_baseline is not None else None
    out["canopy_frac_latest"] = col(canopy_latest)
    out["canopy_year_latest"] = canopy_year_latest if canopy_latest is not None else None
    out["impervious_frac"] = col(impervious)
    out["land_cover_class"] = col(land_cover) if land_cover is not None else None
    out["land_cover_year"] = land_cover_year if land_cover is not None else None
    out["elevation_m"] = col(elevation)

    if population is not None:
        pop = population.reindex(out.index)
        # A cell with no census block centred in it has no residents.
        out["population"] = pop["population"].fillna(0.0)
        out["share_age_65_plus"] = pop["share_age_65_plus"]
        out["share_low_income"] = pop["share_low_income"]
        out["vulnerability_index"] = vulnerability_fn(out)
        out["vulnerable_residents"] = out["population"] * out["vulnerability_index"]
        out.loc[out["population"] == 0, "vulnerable_residents"] = 0.0
    else:
        for name in ("population", "share_age_65_plus", "share_low_income",
                     "vulnerability_index", "vulnerable_residents"):
            out[name] = np.nan
    out["median_household_income"] = np.nan

    if existing_trees is not None:
        out["existing_tree_count"] = existing_trees.reindex(out.index).fillna(0).astype(int)
    else:
        out["existing_tree_count"] = None

    for year_col in ("canopy_year_baseline", "canopy_year_latest", "land_cover_year"):
        out[year_col] = out[year_col].astype("Int64")
    out = out.reset_index()
    return schema.validate(out, "silver.features")
