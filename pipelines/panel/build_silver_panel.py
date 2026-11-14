# Databricks notebook source
"""Bronze -> silver.panel. Runs on Databricks (serverless), not in a Claude session.

Input: the CSVs written by ingest/global/landsat_export.py, uploaded to a Unity
Catalog volume:
    <landing>/<city>_lst_<year>.csv    cell x scene surface temperature
    <landing>/<city>_weather.csv       daily city-mean weather
Output:
    <catalog>.bronze.landsat_lst, <catalog>.bronze.weather_daily   as received
    <catalog>.silver.panel   one row per cell per scene, every cell, no averaging

Re-runnable: each run replaces the tables, so Delta time travel keeps the history
and gold.site_effects can record the panel version it read.
"""
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "heatseeker")  # noqa: F821
dbutils.widgets.text("landing", "/Volumes/heatseeker/bronze/landing/satellite")  # noqa: F821
catalog = dbutils.widgets.get("catalog")  # noqa: F821
landing = dbutils.widgets.get("landing")  # noqa: F821

# A cell-scene row is usable when most of the cell was clear.
MIN_VALID_PIXEL_FRAC = 0.8

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.bronze")  # noqa: F821
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.silver")  # noqa: F821

# COMMAND ----------
# Bronze: as received, plus the role, units, source and license of each source.
lst_raw = (
    spark.read.option("header", True).option("inferSchema", True)  # noqa: F821
    .csv(f"{landing}/*_lst_*.csv")
    .withColumn("role", F.lit("surface_temperature"))
    .withColumn("units", F.lit("K"))
    .withColumn("source", F.lit("Landsat 8/9 Collection 2 Level 2 ST_B10 via Google Earth Engine"))
    .withColumn("license", F.lit("USGS Landsat: public domain"))
    .withColumn("ingested_at_utc", F.current_timestamp())
)
lst_raw.write.mode("overwrite").option("overwriteSchema", True).saveAsTable(f"{catalog}.bronze.landsat_lst")

weather_raw = (
    spark.read.option("header", True).option("inferSchema", True)  # noqa: F821
    .csv(f"{landing}/*_weather.csv")
    .withColumn("role", F.lit("weather"))
    .withColumn("units", F.lit("tmax_k,tmin_k: K; wind_speed_ms: m/s; rh_min_pct: %; precip_mm: mm"))
    .withColumn("source", F.lit("gridMET (IDAHO_EPSCOR/GRIDMET) via Google Earth Engine"))
    .withColumn("license", F.lit("gridMET: public domain"))
    .withColumn("ingested_at_utc", F.current_timestamp())
)
weather_raw.write.mode("overwrite").option("overwriteSchema", True).saveAsTable(f"{catalog}.bronze.weather_daily")

# COMMAND ----------
# Silver: typed, de-duplicated, with per-scene city coverage and same-day weather.
lst = (
    spark.table(f"{catalog}.bronze.landsat_lst")  # noqa: F821
    .withColumn("acquired_at_utc", F.to_timestamp("acquired_at_utc"))
    .withColumn("acquired_date", F.to_date("acquired_at_utc"))
    .withColumn("year", F.year("acquired_at_utc"))
    .dropDuplicates(["city_id", "site_id", "scene_id"])
)

n_cells = lst.groupBy("city_id").agg(F.countDistinct("site_id").alias("n_city_cells"))
scene_cov = (
    lst.groupBy("city_id", "scene_id")
    .agg(F.sum((F.col("valid_pixel_frac") >= MIN_VALID_PIXEL_FRAC).cast("int")).alias("n_clear_cells"))
    .join(n_cells, "city_id")
    .withColumn("city_clear_frac", F.col("n_clear_cells") / F.col("n_city_cells"))
    .select("city_id", "scene_id", "city_clear_frac")
)

weather = spark.table(f"{catalog}.bronze.weather_daily").select(  # noqa: F821
    "city_id",
    F.to_date("date").alias("acquired_date"),
    (F.col("tmax_k") - 273.15).alias("tmax_c"),
    (F.col("tmin_k") - 273.15).alias("tmin_c"),
    "wind_speed_ms",
    "precip_mm",
)

panel = (
    lst.join(scene_cov, ["city_id", "scene_id"], "left")
    .join(weather, ["city_id", "acquired_date"], "left")
    .select(
        "country_code", "city_id", "site_id", "scene_id",
        "acquired_at_utc", "acquired_date", "year", "sensor",
        F.col("lst_mean_k").cast("double"), F.col("lst_median_k").cast("double"), F.col("lst_std_k").cast("double"),
        F.col("valid_pixel_count").cast("int"), F.col("valid_pixel_frac").cast("double"),
        (F.col("valid_pixel_frac") >= MIN_VALID_PIXEL_FRAC).alias("is_clear"),
        F.col("scene_cloud_cover_frac").cast("double"), "city_clear_frac",
        F.col("sun_elevation_deg").cast("double"), F.col("wrs_path").cast("int"), F.col("wrs_row").cast("int"),
        "tmax_c", "tmin_c", "wind_speed_ms", "precip_mm",
        "source", "license",
    )
)
panel.write.mode("overwrite").option("overwriteSchema", True).saveAsTable(f"{catalog}.silver.panel")

# COMMAND ----------
display(  # noqa: F821
    spark.sql(  # noqa: F821
        f"""SELECT city_id, sensor, year, count(DISTINCT scene_id) scenes, count(*) row_count,
                   round(avg(valid_pixel_frac), 3) avg_valid_frac, round(avg(lst_median_k) - 273.15, 1) avg_lst_c
            FROM {catalog}.silver.panel GROUP BY ALL ORDER BY city_id, year, sensor"""
    )
)
