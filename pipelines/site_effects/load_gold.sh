#!/usr/bin/env bash
# Load a locally produced gold.site_effects CSV into Unity Catalog as a Delta table, using only
# the Databricks CLI and the serverless SQL warehouse (no cluster, no Spark on the laptop).
#
#   pipelines/site_effects/load_gold.sh pipelines/site_effects/out/nyc_gold_site_effects.csv nyc [profile] [catalog]
#
# Steps: copy the file to /Volumes/<catalog>/gold/files/site_effects/, then
# CREATE TABLE IF NOT EXISTS + DELETE the city's rows + INSERT from read_files(). Rerunnable.
set -euo pipefail

CSV="${1:?csv path}"
CITY="${2:?city_id}"
PROFILE="${3:-heatseeker}"
CATALOG="${4:-heatseeker}"
TABLE="${CATALOG}.gold.site_effects"
VOL="/Volumes/${CATALOG}/gold/files/site_effects"
DEST="${VOL}/$(basename "$CSV")"

WH=$(databricks warehouses list -p "$PROFILE" -o json | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['id'])")

run_sql() {
  local sql="$1"
  databricks api post /api/2.0/sql/statements -p "$PROFILE" \
    --json "$(python3 -c "import json,sys; print(json.dumps({'warehouse_id': sys.argv[1], 'statement': sys.argv[2], 'wait_timeout': '50s', 'on_wait_timeout': 'CANCEL'}))" "$WH" "$sql")" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); s=d['status']; print(s['state'], (s.get('error') or {}).get('message','')); sys.exit(0 if s['state']=='SUCCEEDED' else 1)"
}

echo "[load_gold] uploading $CSV -> $DEST"
databricks fs mkdir "dbfs:$VOL" -p "$PROFILE" 2>/dev/null || true
databricks fs cp "$CSV" "dbfs:$DEST" --overwrite -p "$PROFILE"

echo "[load_gold] creating table if needed"
run_sql "CREATE TABLE IF NOT EXISTS ${TABLE} (
  country_code STRING, city_id STRING, site_id STRING, variant STRING, treatment_year INT,
  intervention_type STRING, dose_trees INT, n_pre_scenes INT, n_post_scenes INT, n_controls INT,
  effect_k DOUBLE, effect_se_k DOUBLE, ci_low_k DOUBLE, ci_high_k DOUBLE, placebo_p DOUBLE, mde_k DOUBLE,
  quality_label STRING, event_study_json STRING, panel_version STRING, method_version STRING,
  evaluated_at_utc TIMESTAMP
) USING DELTA COMMENT 'Measured surface-temperature effect per planted H3 cell vs matched unplanted cells. Kelvin differences; negative = cooling. Surface temperature is not felt temperature.'"

echo "[load_gold] replacing rows for city_id=${CITY}"
run_sql "DELETE FROM ${TABLE} WHERE city_id = '${CITY}'"
run_sql "INSERT INTO ${TABLE}
SELECT country_code, city_id, site_id, variant, CAST(treatment_year AS INT), intervention_type,
       CAST(dose_trees AS INT), CAST(n_pre_scenes AS INT), CAST(n_post_scenes AS INT), CAST(n_controls AS INT),
       CAST(effect_k AS DOUBLE), CAST(effect_se_k AS DOUBLE), CAST(ci_low_k AS DOUBLE), CAST(ci_high_k AS DOUBLE),
       CAST(placebo_p AS DOUBLE), CAST(mde_k AS DOUBLE), quality_label, event_study_json,
       CAST(panel_version AS STRING), method_version, CAST(evaluated_at_utc AS TIMESTAMP)
FROM read_files('${DEST}', format => 'csv', header => true, inferSchema => false)
WHERE city_id = '${CITY}'"

run_sql "SELECT variant, quality_label, COUNT(*) AS n FROM ${TABLE} WHERE city_id = '${CITY}' GROUP BY ALL ORDER BY ALL" || true
echo "[load_gold] done: ${TABLE}"
