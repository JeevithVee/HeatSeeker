#!/usr/bin/env bash
# Usage: load_gold.sh <gold.csv> <city_id> [profile] [catalog]
set -euo pipefail
exec python3 "$(dirname "$0")/load_gold.py" "$@"
