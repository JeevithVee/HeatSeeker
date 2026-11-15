"""HeatSeeker website: static pages plus the planting log.

The pages read precomputed JSON under static/data (written by build_data.py
from the standard tables), so the site still works when no warehouse is
reachable. The only thing the server stores is plantings logged in the tool.

    uvicorn server:app --app-dir web --port 8600
"""
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
LOG_PATH = Path(os.environ.get("HEATSEEKER_LOG_DIR", HERE / "var")) / "plantings.jsonl"

META = json.loads((STATIC / "data" / "meta.json").read_text())
CITY_IDS = {c["city_id"] for c in META["cities"]}
INTERVENTIONS = set(META["costs_usd"])
_city_cells = {}

app = FastAPI(title="HeatSeeker", docs_url=None, redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1024)


def cells_of(city_id):
    """Site ids of a city, read once from its map file."""
    if city_id not in _city_cells:
        gj = json.loads((STATIC / "data" / f"{city_id}.geojson").read_text())
        _city_cells[city_id] = {f["properties"]["id"] for f in gj["features"]}
    return _city_cells[city_id]


class Planting(BaseModel):
    city_id: str
    site_id: str
    planted_date: date
    intervention_type: str
    trees_planted: int = Field(ge=1, le=5000)
    cost_usd: float | None = Field(default=None, ge=0, le=50_000_000)
    note: str | None = Field(default=None, max_length=280)


def read_log():
    if not LOG_PATH.exists():
        return []
    return [json.loads(line) for line in LOG_PATH.read_text().splitlines() if line.strip()]


@app.get("/api/plantings")
def list_plantings(city_id: str | None = None):
    rows = read_log()
    return [r for r in rows if city_id is None or r["city_id"] == city_id]


@app.post("/api/plantings", status_code=201)
def log_planting(p: Planting):
    if p.city_id not in CITY_IDS:
        raise HTTPException(422, "Unknown city.")
    if p.site_id not in cells_of(p.city_id):
        raise HTTPException(422, "That cell is not in this city's grid.")
    if p.intervention_type not in INTERVENTIONS:
        raise HTTPException(422, "Unknown intervention type.")
    # One day of slack: the browser's calendar day can be ahead of the server's.
    if p.planted_date > date.today() + timedelta(days=1):
        raise HTTPException(422, "The planting date is in the future.")
    row = {
        "country_code": "US",
        "city_id": p.city_id,
        "site_id": p.site_id,
        "planted_date": p.planted_date.isoformat(),
        "plant_year": p.planted_date.year,
        "intervention_type": p.intervention_type,
        "trees_planted": p.trees_planted,
        "cost_usd": p.cost_usd,
        "note": p.note,
        "source": "heatseeker_web",
        "logged_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(row) + "\n")
    return row


@app.get("/dashboard")
def dashboard():
    return FileResponse(STATIC / "dashboard.html")


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
