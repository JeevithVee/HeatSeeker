"""Create/replace the HeatSeeker AI/BI (Lakeview) portfolio dashboard.

    python app/create_dashboard.py [--host ...] [--warehouse-id ...]

Reads only gold tables (shared rule 12). Panels: evaluation outcomes per
city, detected direction split, top recommendations, predicted cooling vs
vulnerable residents. The rule-14 caveat is printed on the page.
"""

from __future__ import annotations

import argparse
import json

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dashboards import Dashboard

NAME = "HeatSeeker Portfolio"

CAVEAT = (
    "Surface temperature at the satellite overpass, not air or felt "
    "temperature. 'Detected' is an unadjusted statistical label, not proof of "
    "causal cooling. Reliable cooling is not established: sensitivity "
    "intervals span zero, NYC's pooled cooling is indistinguishable from zero "
    "under alternative specifications, and Seattle shows a negative "
    "association, not a causal estimate. All four cities are temperate."
)


def counter(name, ds, expr, title, x, y, w=1, h=3):
    return {
        "widget": {
            "name": name,
            "queries": [{"name": "q", "query": {
                "datasetName": ds, "disaggregated": False,
                "fields": [{"name": "v", "expression": expr}]}}],
            "spec": {"version": 2, "widgetType": "counter",
                     "frame": {"title": title, "showTitle": True},
                     "encodings": {"value": {"fieldName": "v",
                                             "displayName": title}}},
        },
        "position": {"x": x, "y": y, "width": w, "height": h},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="https://dbc-f8d41fd5-0183.cloud.databricks.com")
    ap.add_argument("--warehouse-id", default="b646c232444bafe7")
    args = ap.parse_args()

    datasets = [
        {"name": "effects", "displayName": "Site effects (headline variant)",
         "queryLines": [
             "SELECT city_id, quality_label, effect_k,",
             "  CASE WHEN quality_label = 'detected' AND effect_k < 0 THEN 'detected cooling'",
             "       WHEN quality_label = 'detected' THEN 'detected warming'",
             "       ELSE quality_label END AS outcome",
             "FROM heatseeker.gold.site_effects WHERE variant = 'all'"]},
        {"name": "recs", "displayName": "Recommendations",
         "queryLines": [
             "SELECT city_id, rank, site_id, score,",
             "  predicted_cooling_k_15y, vulnerable_residents, est_cost_usd,",
             "  suggested_intervention, holdout_control",
             "FROM heatseeker.gold.recommendations"]},
    ]

    widgets = [
        {"widget": {"name": "caveat",
                    "textbox_spec": f"### HeatSeeker portfolio\n{CAVEAT}"},
         "position": {"x": 0, "y": 0, "width": 6, "height": 2}},
        counter("c_eval", "effects", "COUNT(*)", "Sites evaluated", 0, 2),
        counter("c_cool", "effects",
                "COUNT(CASE WHEN outcome = 'detected cooling' THEN 1 END)",
                "Detected cooling", 1, 2),
        counter("c_warm", "effects",
                "COUNT(CASE WHEN outcome = 'detected warming' THEN 1 END)",
                "Detected warming", 2, 2),
        counter("c_recs", "recs", "COUNT(*)", "Recommended cells", 3, 2),
        counter("c_hold", "recs",
                "COUNT(CASE WHEN holdout_control THEN 1 END)",
                "Holdout controls", 4, 2),
        counter("c_vuln", "recs", "SUM(`vulnerable_residents`)",
                "Vulnerable residents reached", 5, 2),
        {"widget": {
            "name": "bar_outcomes",
            "queries": [{"name": "q", "query": {
                "datasetName": "effects", "disaggregated": False,
                "fields": [{"name": "city_id", "expression": "`city_id`"},
                           {"name": "outcome", "expression": "`outcome`"},
                           {"name": "n", "expression": "COUNT(*)"}]}}],
            "spec": {"version": 3, "widgetType": "bar",
                     "frame": {"title": "Evaluation outcomes by city",
                               "showTitle": True},
                     "encodings": {
                         "x": {"fieldName": "city_id", "scale": {"type": "categorical"}, "displayName": "city"},
                         "y": {"fieldName": "n", "scale": {"type": "quantitative"}, "displayName": "sites"},
                         "color": {"fieldName": "outcome", "scale": {"type": "categorical"}, "displayName": "outcome"}}},
        }, "position": {"x": 0, "y": 5, "width": 3, "height": 7}},
        {"widget": {
            "name": "scatter_recs",
            "queries": [{"name": "q", "query": {
                "datasetName": "recs", "disaggregated": True,
                "fields": [{"name": "predicted_cooling_k_15y", "expression": "`predicted_cooling_k_15y`"},
                           {"name": "vulnerable_residents", "expression": "`vulnerable_residents`"},
                           {"name": "city_id", "expression": "`city_id`"}]}}],
            "spec": {"version": 3, "widgetType": "scatter",
                     "frame": {"title": "Predicted cooling at 15y (K) vs vulnerable residents",
                               "showTitle": True},
                     "encodings": {
                         "x": {"fieldName": "predicted_cooling_k_15y", "scale": {"type": "quantitative"}, "displayName": "predicted cooling 15y (K)"},
                         "y": {"fieldName": "vulnerable_residents", "scale": {"type": "quantitative"}, "displayName": "vulnerable residents"},
                         "color": {"fieldName": "city_id", "scale": {"type": "categorical"}, "displayName": "city"}}},
        }, "position": {"x": 3, "y": 5, "width": 3, "height": 7}},
        {"widget": {
            "name": "table_top",
            "queries": [{"name": "q", "query": {
                "datasetName": "recs", "disaggregated": True,
                "fields": [{"name": c, "expression": f"`{c}`"} for c in
                           ["city_id", "rank", "site_id",
                            "predicted_cooling_k_15y", "vulnerable_residents",
                            "est_cost_usd", "suggested_intervention",
                            "holdout_control"]]}}],
            "spec": {"version": 1, "widgetType": "table",
                     "frame": {"title": "Top 10 per city (filter with the rank column)",
                               "showTitle": True},
                     "encodings": {"columns": [
                         {"fieldName": c, "displayName": c} for c in
                         ["city_id", "rank", "site_id",
                          "predicted_cooling_k_15y", "vulnerable_residents",
                          "est_cost_usd", "suggested_intervention",
                          "holdout_control"]]}},
        }, "position": {"x": 0, "y": 12, "width": 6, "height": 8}},
    ]

    serialized = json.dumps({
        "datasets": datasets,
        "pages": [{"name": "portfolio", "displayName": "Portfolio",
                   "layout": widgets}],
    })

    w = WorkspaceClient(host=args.host, auth_type="external-browser")
    existing = [d for d in w.lakeview.list()
                if d.display_name == NAME]
    if existing:
        d = w.lakeview.update(existing[0].dashboard_id, Dashboard(
            display_name=NAME, warehouse_id=args.warehouse_id,
            serialized_dashboard=serialized))
        print("updated:", d.dashboard_id)
    else:
        d = w.lakeview.create(Dashboard(
            display_name=NAME, warehouse_id=args.warehouse_id,
            serialized_dashboard=serialized))
        print("created:", d.dashboard_id)
    print(f"URL: {args.host}/sql/dashboardsv3/{d.dashboard_id}")


if __name__ == "__main__":
    main()
