"""Earth Engine export: Landsat 8/9 summer surface temperature per H3 cell.

Earth Engine does the cloud masking, the conversion to Kelvin and the per-cell
zonal statistics. We export TABLES (CSV), never rasters: one row per cell per
scene, for every cell in the city grid, planted or not.

Three kinds of task are started:
  lst      one task per year: cell x scene surface temperature statistics
  weather  one task: gridMET daily city-mean weather for the same summer days
  static   one task: per-cell elevation (and anything else that never changes)

Country-agnostic: the grid CSV (from build_grid.py) is the only city input.

    python ingest/global/landsat_export.py --project MY_EE_PROJECT \
        --grid ingest/global/grids/nyc_h3_res9.csv --dest drive --folder heatseeker_nyc

Surface temperature is not felt (air) temperature.
"""
import argparse
import csv

import ee
import h3

LANDSAT = {
    "LANDSAT_8": "LANDSAT/LC08/C02/T1_L2",
    "LANDSAT_9": "LANDSAT/LC09/C02/T1_L2",
}
# Collection 2 Level 2 surface temperature scaling: Kelvin = DN * scale + offset
ST_SCALE, ST_OFFSET = 0.00341802, 149.0
# QA_PIXEL bits to reject: 0 fill, 1 dilated cloud, 2 cirrus, 3 cloud, 4 cloud shadow
QA_REJECT = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4)

LST_COLUMNS = [
    "country_code", "city_id", "site_id", "scene_id", "acquired_at_utc", "sensor",
    "lst_mean_k", "lst_median_k", "lst_std_k", "valid_pixel_count", "valid_pixel_frac",
    "scene_cloud_cover_frac", "sun_elevation_deg", "wrs_path", "wrs_row",
]


def load_grid(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def grid_to_fc(rows):
    feats = []
    for r in rows:
        ring = [[lon, lat] for lat, lon in h3.cell_to_boundary(r["site_id"])]
        ring.append(ring[0])
        feats.append(
            ee.Feature(
                ee.Geometry.Polygon([ring], None, False),
                {"site_id": r["site_id"], "city_id": r["city_id"], "country_code": r["country_code"]},
            )
        )
    return ee.FeatureCollection(feats)


def scenes(region, year, months, max_cloud):
    col = None
    for coll_id in LANDSAT.values():
        c = (
            ee.ImageCollection(coll_id)
            .filterBounds(region)
            .filter(ee.Filter.calendarRange(year, year, "year"))
            .filter(ee.Filter.calendarRange(months[0], months[1], "month"))
            .filter(ee.Filter.lt("CLOUD_COVER", max_cloud))
        )
        col = c if col is None else col.merge(c)
    return col


def cell_stats(cells):
    reducer = (
        ee.Reducer.mean()
        .combine(ee.Reducer.median(), sharedInputs=True)
        .combine(ee.Reducer.stdDev(), sharedInputs=True)
        .combine(ee.Reducer.count(), sharedInputs=True)
    )

    def per_image(img):
        clear = img.select("QA_PIXEL").bitwiseAnd(QA_REJECT).eq(0).And(img.select("ST_B10").gt(0))
        lst = img.select("ST_B10").multiply(ST_SCALE).add(ST_OFFSET).updateMask(clear).rename("lst")
        valid = clear.unmask(0).rename("valid")
        stats = lst.addBands(valid).reduceRegions(collection=cells, reducer=reducer, scale=30, tileScale=4)
        props = {
            "scene_id": img.get("LANDSAT_PRODUCT_ID"),
            "acquired_at_utc": img.date().format("YYYY-MM-dd'T'HH:mm:ss'Z'"),
            "sensor": img.get("SPACECRAFT_ID"),
            "scene_cloud_cover_frac": ee.Number(img.get("CLOUD_COVER")).divide(100),
            "sun_elevation_deg": img.get("SUN_ELEVATION"),
            "wrs_path": img.get("WRS_PATH"),
            "wrs_row": img.get("WRS_ROW"),
        }

        def tidy(f):
            return ee.Feature(None, props).set(
                {
                    "country_code": f.get("country_code"),
                    "city_id": f.get("city_id"),
                    "site_id": f.get("site_id"),
                    "lst_mean_k": f.get("lst_mean"),
                    "lst_median_k": f.get("lst_median"),
                    "lst_std_k": f.get("lst_stdDev"),
                    "valid_pixel_count": f.get("lst_count"),
                    "valid_pixel_frac": f.get("valid_mean"),
                }
            )

        # Cells with no clear pixel in this scene carry no information: drop them.
        return stats.filter(ee.Filter.gt("lst_count", 0)).map(tidy)

    return per_image


def export_table(fc, name, columns, args):
    common = dict(collection=fc, description=name, fileFormat="CSV", selectors=columns)
    if args.dest == "gcs":
        task = ee.batch.Export.table.toCloudStorage(bucket=args.bucket, fileNamePrefix=f"{args.folder}/{name}", **common)
    else:
        task = ee.batch.Export.table.toDrive(folder=args.folder, fileNamePrefix=name, **common)
    task.start()
    print(f"started {name}: {task.id}")
    return task


def weather_fc(region, city_id, country_code, start_year, end_year, months):
    col = (
        ee.ImageCollection("IDAHO_EPSCOR/GRIDMET")
        .filter(ee.Filter.calendarRange(start_year, end_year, "year"))
        .filter(ee.Filter.calendarRange(months[0], months[1], "month"))
        .select(["tmmx", "tmmn", "vs", "rmin", "pr"])
    )

    def per_day(img):
        m = img.reduceRegion(ee.Reducer.mean(), region, 4000)
        return ee.Feature(
            None,
            {
                "country_code": country_code,
                "city_id": city_id,
                "date": img.date().format("YYYY-MM-dd"),
                "tmax_k": m.get("tmmx"),
                "tmin_k": m.get("tmmn"),
                "wind_speed_ms": m.get("vs"),
                "rh_min_pct": m.get("rmin"),
                "precip_mm": m.get("pr"),
                "weather_source": "gridMET",
            },
        )

    return ee.FeatureCollection(col.map(per_day))


WEATHER_COLUMNS = ["country_code", "city_id", "date", "tmax_k", "tmin_k", "wind_speed_ms", "rh_min_pct", "precip_mm", "weather_source"]


def static_fc(cells, elevation_asset, elevation_band):
    elev = ee.Image(elevation_asset).select(elevation_band).rename("elevation_m")
    stats = elev.reduceRegions(collection=cells, reducer=ee.Reducer.mean(), scale=30, tileScale=4)
    return stats.map(
        lambda f: ee.Feature(
            None,
            {
                "country_code": f.get("country_code"),
                "city_id": f.get("city_id"),
                "site_id": f.get("site_id"),
                "elevation_m": f.get("mean"),
                "elevation_source": elevation_asset,
            },
        )
    )


STATIC_COLUMNS = ["country_code", "city_id", "site_id", "elevation_m", "elevation_source"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True, help="Earth Engine enabled Google Cloud project id")
    p.add_argument("--grid", required=True)
    p.add_argument("--dest", choices=["drive", "gcs"], default="drive")
    p.add_argument("--bucket")
    p.add_argument("--folder", default="heatseeker")
    p.add_argument("--start-year", type=int, default=2013)
    p.add_argument("--end-year", type=int, default=2026)
    p.add_argument("--months", type=int, nargs=2, default=[6, 8], help="first and last summer month")
    p.add_argument("--max-scene-cloud", type=float, default=60, help="scene-level CLOUD_COVER ceiling, percent")
    p.add_argument("--elevation-asset", default="USGS/SRTMGL1_003")
    p.add_argument("--elevation-band", default="elevation")
    p.add_argument("--only", choices=["lst", "weather", "static"], nargs="*", default=["lst", "weather", "static"])
    p.add_argument("--dry-run", action="store_true", help="print scene counts, start nothing")
    args = p.parse_args()

    ee.Initialize(project=args.project)
    rows = load_grid(args.grid)
    city_id, country_code = rows[0]["city_id"], rows[0]["country_code"]
    cells = grid_to_fc(rows)
    lats = [float(r["centroid_lat"]) for r in rows]
    lons = [float(r["centroid_lon"]) for r in rows]
    region = ee.Geometry.Rectangle([min(lons), min(lats), max(lons), max(lats)])
    print(f"{city_id}: {len(rows)} cells")

    if "lst" in args.only:
        for year in range(args.start_year, args.end_year + 1):
            col = scenes(region, year, args.months, args.max_scene_cloud)
            n = col.size().getInfo()
            print(f"{year}: {n} scenes")
            if n == 0 or args.dry_run:
                continue
            fc = ee.FeatureCollection(col.map(cell_stats(cells))).flatten()
            export_table(fc, f"{city_id}_lst_{year}", LST_COLUMNS, args)
    if args.dry_run:
        return
    if "weather" in args.only:
        export_table(
            weather_fc(region, city_id, country_code, args.start_year, args.end_year, args.months),
            f"{city_id}_weather", WEATHER_COLUMNS, args,
        )
    if "static" in args.only:
        export_table(static_fc(cells, args.elevation_asset, args.elevation_band), f"{city_id}_static", STATIC_COLUMNS, args)


if __name__ == "__main__":
    main()
