"""Zonal statistics and population allocation on tiny hand-made inputs."""
import h3
import numpy as np
import pandas as pd

import schema
from pipelines import features

RES = schema.H3_RESOLUTION
CELL_A = h3.latlng_to_cell(40.70, -73.95, RES)
CELL_B = h3.latlng_to_cell(40.75, -73.80, RES)


def test_zonal_mean_ignores_fill_values():
    site_ids = np.array([CELL_A, CELL_A, CELL_A, CELL_B])
    values = np.array([10, 30, 255, 50], dtype="uint8")
    out = features.zonal_mean_fraction(site_ids, values)
    assert out[CELL_A] == 0.20 and out[CELL_B] == 0.50


def test_zonal_dominant_class():
    site_ids = np.array([CELL_A, CELL_A, CELL_A, CELL_B, CELL_B])
    values = np.array([23, 23, 11, 250, 41], dtype="uint8")
    out = features.zonal_dominant_class(site_ids, values, {23: "developed", 41: "forest"})
    assert out[CELL_A] == "developed" and out[CELL_B] == "forest"


def test_population_shares_are_population_weighted():
    lat_a, lon_a = h3.cell_to_latlng(CELL_A)
    blocks = pd.DataFrame({
        "lat": [lat_a, lat_a], "lon": [lon_a, lon_a], "population": [100.0, 300.0],
        "share_age_65_plus": [0.10, 0.30], "share_low_income": [0.20, np.nan],
    })
    out = features.population_by_cell(blocks)
    assert out.loc[CELL_A, "population"] == 400.0
    assert np.isclose(out.loc[CELL_A, "share_age_65_plus"], 0.25)
    assert np.isclose(out.loc[CELL_A, "share_low_income"], 0.20)   # unknown block left out


def test_build_features_covers_every_grid_cell():
    grid = pd.DataFrame({
        "country_code": "US", "city_id": "nyc", "site_id": [CELL_A, CELL_B],
        "centroid_lat": [40.70, 40.75], "centroid_lon": [-73.95, -73.80], "area_km2": [0.105, 0.105],
    })
    pop = pd.DataFrame({"population": [400.0], "share_age_65_plus": [0.25], "share_low_income": [0.2]},
                       index=[CELL_A])
    out = features.build_features(grid, canopy_baseline=pd.Series({CELL_A: 0.1}),
                                  canopy_year_baseline=2014, population=pop)
    assert list(out.columns) == schema.columns("silver.features")
    b = out.set_index("site_id").loc[CELL_B]
    assert b["population"] == 0 and b["vulnerable_residents"] == 0 and np.isnan(b["canopy_frac_baseline"])
