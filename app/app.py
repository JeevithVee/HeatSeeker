"""HeatSeeker app: Recommend / Track / Results.

Streamlit app structured to run as a Databricks App. All numbers shown come
from the gold/silver tables (shared rule 12); units and labels come from
/config/us (shared rule 10). Storage is Celsius; display defaults to
Fahrenheit per config.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

import data

st.set_page_config(page_title="HeatSeeker", page_icon="🌳", layout="wide")

CONFIG = data.load_config()
FAHRENHEIT = CONFIG["display"]["temperature_unit"] == "fahrenheit"
UNIT = "°F" if FAHRENHEIT else "°C"

CAVEAT = (
    "**Surface temperature is not felt (air) temperature** - effects here are "
    "satellite-measured land surface temperature. All four cities are "
    "temperate; results have not been tested in hot, dry climates."
)

QUALITY_COLORS = {
    "detected": [46, 125, 50],
    "inconclusive": [245, 158, 11],
    "not_detectable": [120, 120, 120],
}


def dc(celsius_delta):
    """Convert a temperature *difference* to display units (ΔF = ΔC × 1.8)."""
    return celsius_delta * 1.8 if FAHRENHEIT else celsius_delta


@st.cache_data(ttl=300)
def tables():
    return {name: data.load_table(name) for name in data.TABLES}


def deck_map(df: pd.DataFrame, colors: np.ndarray, radius: int = 120,
             tooltip_cols: list[str] | None = None) -> None:
    d = df.copy()
    d[["r", "g", "b"]] = np.asarray(colors, dtype=int)
    tip = None
    if tooltip_cols:
        tip = {"text": "\n".join(f"{c}: {{{c}}}" for c in tooltip_cols)}
    city = CONFIG["cities"][0]["center"]
    st.pydeck_chart(pdk.Deck(
        map_style=None,
        initial_view_state=pdk.ViewState(
            latitude=city["lat"], longitude=city["lon"], zoom=10.3),
        layers=[pdk.Layer(
            "ScatterplotLayer", d,
            get_position=["lon", "lat"], get_fill_color=["r", "g", "b", 170],
            get_radius=radius, pickable=bool(tip),
        )],
        tooltip=tip,
    ))


# ---------------------------------------------------------------- Recommend

def view_recommend(t):
    recs, feats = t["recommendations"], t["features"]
    if recs.empty:
        st.warning("No recommendations yet - run the Learn + Plan pipeline.")
        return

    st.subheader("Where to plant next")
    st.caption("Ranked by predicted cooling × vulnerable residents ÷ cost. "
               "Every 5th site is held out unplanted as a future control.")

    c1, c2, c3 = st.columns(3)
    top_n = c1.slider("Show top N sites", 25, len(recs), 150, step=25)
    kinds = c2.multiselect("Intervention", sorted(recs["suggested_intervention"].unique()),
                           default=sorted(recs["suggested_intervention"].unique()))
    show_holdout = c3.checkbox("Include holdout controls", value=True)

    d = recs[recs["suggested_intervention"].isin(kinds)]
    if not show_holdout:
        d = d[~d["holdout_control"]]
    d = d.nsmallest(top_n, "rank").copy()

    # color by score percentile: deep red = top priority
    q = d["score"].rank(pct=True).to_numpy()
    colors = np.stack([60 + 195 * q, 80 + 60 * (1 - q), 60 * (1 - q)], axis=1)
    d["cooling_15y"] = dc(d["predicted_cooling_c_15y"]).round(2)
    deck_map(d, colors, tooltip_cols=["site_id", "rank", "cooling_15y",
                                      "suggested_intervention"])

    site = st.selectbox("Site detail", d.sort_values("rank")["site_id"])
    r = d[d["site_id"] == site].iloc[0]
    f = feats[feats["site_id"] == site].iloc[0]

    m = st.columns(5)
    m[0].metric("Rank", int(r["rank"]))
    m[1].metric(f"Predicted cooling at 15y ({UNIT})",
                f"{dc(r['predicted_cooling_c_15y']):.2f}",
                f"range {dc(r['predicted_cooling_c_15y_low']):.2f} to "
                f"{dc(r['predicted_cooling_c_15y_high']):.2f}", delta_color="off")
    m[2].metric("Vulnerable residents", f"{r['vulnerable_residents']:,.0f}")
    m[3].metric("Est. cost", f"${r['est_cost_usd']:,.0f}")
    m[4].metric("Suggestion", r["suggested_intervention"].replace("_", " "))
    st.caption(
        f"Why: canopy {f['canopy_pct']:.0f}%, impervious {f['impervious_pct']:.0f}%, "
        f"population {f['population']:,.0f}. Cooling at 5y: "
        f"{dc(r['predicted_cooling_c_5y']):.2f} {UNIT} "
        f"(trees reach ~{CONFIG['cooling_maturity']['year_5']:.0%} of mature effect). "
        + ("**Held out as a control - do not plant.**" if r["holdout_control"] else "")
    )

    st.dataframe(
        d.sort_values("rank")[
            ["rank", "site_id", "cooling_15y", "vulnerable_residents",
             "est_cost_usd", "suggested_intervention", "holdout_control"]
        ].rename(columns={"cooling_15y": f"cooling 15y ({UNIT})"}),
        width="stretch", hide_index=True, height=300,
    )


# ------------------------------------------------------------------- Track

def view_track(t):
    inter, feats = t["interventions"], t["features"]
    st.subheader("What has been planted")
    st.caption("Logged plantings start the next Prove → Learn cycle.")

    if not inter.empty:
        d = inter.merge(feats[["site_id", "lat", "lon"]], on="site_id")
        q = (d["trees_planted"] / d["trees_planted"].max()).to_numpy()
        colors = np.stack([40 * (1 - q), 90 + 110 * q, 60 * (1 - q)], axis=1)
        deck_map(d, colors, tooltip_cols=["site_id", "trees_planted", "plant_year"])
        c = st.columns(3)
        c[0].metric("Sites planted", len(d))
        c[1].metric("Trees planted", f"{d['trees_planted'].sum():,.0f}")
        c[2].metric("Years", f"{d['plant_year'].min()}-{d['plant_year'].max()}")

    st.divider()
    st.markdown("**Log a new planting**")
    with st.form("log_planting"):
        c = st.columns(5)
        site = c[0].selectbox("Site (H3 cell)", feats["site_id"])
        kind = c[1].selectbox("Type", list(CONFIG["costs_usd"]))
        n = c[2].number_input("Trees / units", 1, 500, 30)
        when = c[3].date_input("Date", date.today())
        cost = c[4].number_input("Cost (USD)", 0, 500000,
                                 int(CONFIG["costs_usd"]["street_trees"]))
        if st.form_submit_button("Log it"):
            data.log_planting({
                "country_code": "US", "city_id": "nyc", "site_id": site,
                "intervention_type": kind, "trees_planted": int(n),
                "planted_date": str(when), "cost_usd": float(cost),
                "logged_at": datetime.now(timezone.utc).isoformat(),
            })
            st.success(f"Logged {n} × {kind} at {site}. It will be evaluated "
                       "against matched controls once enough post-planting scenes arrive.")

    new = data.load_new_plantings()
    if not new.empty:
        st.dataframe(new, width="stretch", hide_index=True)


# ----------------------------------------------------------------- Results

def view_results(t):
    eff, feats, panel = t["site_effects"], t["features"], t["panel_sample"]
    if eff.empty:
        st.warning("No measured effects yet - waiting on gold.site_effects.")
        return

    st.subheader("Did past plantings cool anything?")
    counts = eff["quality_label"].value_counts()
    detected = eff[eff["quality_label"] == "detected"]

    m = st.columns(4)
    m[0].metric("Sites evaluated", len(eff))
    m[1].metric("Cooling detected", int(counts.get("detected", 0)))
    m[2].metric("Not detectable", int(counts.get("not_detectable", 0)),
                help="Honestly reported: no effect visible at 30 m resolution.")
    med = dc(detected["effect_c"].median()) if len(detected) else float("nan")
    m[3].metric(f"Median detected effect ({UNIT})", f"{med:.2f}")

    labels = st.multiselect("Quality label", list(QUALITY_COLORS),
                            default=list(QUALITY_COLORS))
    d = eff[eff["quality_label"].isin(labels)].merge(
        feats[["site_id", "lat", "lon"]], on="site_id")
    d["effect_display"] = dc(d["effect_c"]).round(2)
    deck_map(d, np.array([QUALITY_COLORS[q] for q in d["quality_label"]]),
             tooltip_cols=["site_id", "effect_display", "quality_label"])
    st.caption("Green = cooling detected · amber = inconclusive · grey = not detectable")

    # Portfolio: cooling per dollar, using config planting costs as estimates.
    cost_per_site = CONFIG["costs_usd"]["street_trees"]
    if len(detected):
        total_cooling = dc(-detected["effect_c"].sum())
        st.caption(
            f"Portfolio: {total_cooling:.1f} {UNIT} of detected cooling across "
            f"{len(detected)} sites ≈ "
            f"{total_cooling / (len(detected) * cost_per_site) * 10000:.2f} {UNIT} "
            f"per $10k (at ~${cost_per_site:,} per planted cell, config estimate)."
        )

    st.divider()
    st.markdown("**Site detail - before / after vs matched controls**")
    site = st.selectbox("Evaluated site", d["site_id"])
    r = eff[eff["site_id"] == site].iloc[0]

    m = st.columns(4)
    m[0].metric(f"Measured effect ({UNIT})", f"{dc(r['effect_c']):.2f}",
                f"CI {dc(r['effect_ci_low_c']):.2f} to {dc(r['effect_ci_high_c']):.2f}",
                delta_color="off")
    m[1].metric("Confidence", r["quality_label"].replace("_", " "))
    m[2].metric("Scenes pre / post", f"{r['n_scenes_pre']} / {r['n_scenes_post']}")
    m[3].metric("Method", r["method"])

    p = panel[panel["site_id"] == site]
    if not p.empty:
        long = p.melt(
            id_vars=["scene_date", "post"],
            value_vars=["site_temp_rel_c", "control_temp_rel_c"],
            var_name="series", value_name="temp_rel_c",
        )
        long["series"] = long["series"].map(
            {"site_temp_rel_c": "this site", "control_temp_rel_c": "matched controls"})
        long["temp_rel"] = dc(long["temp_rel_c"])
        plant_date = p.loc[p["post"], "scene_date"].min()
        chart = alt.Chart(long).mark_line(point=True).encode(
            x=alt.X("scene_date:T", title="clear-sky summer scene"),
            y=alt.Y("temp_rel:Q", title=f"surface temp vs city baseline ({UNIT})"),
            color=alt.Color("series:N", title=None,
                            scale=alt.Scale(range=["#2e7d32", "#9e9e9e"])),
        )
        rule = alt.Chart(pd.DataFrame({"d": [plant_date]})).mark_rule(
            strokeDash=[4, 4], color="#c62828").encode(x="d:T")
        st.altair_chart(chart + rule, width="stretch")
        st.caption("Dashed red line: planting. If the green line drops below "
                   "grey after it, the site cooled relative to its matched controls.")


# -------------------------------------------------------------------- main

st.title("🌳 HeatSeeker")
st.caption("Plan, plant, prove: urban cooling for US cities · New York prototype")

view = st.sidebar.radio("View", ["Recommend", "Track", "Results"])
st.sidebar.divider()
st.sidebar.info(CAVEAT)

t = tables()
{"Recommend": view_recommend, "Track": view_track, "Results": view_results}[view](t)

st.divider()
st.caption(CAVEAT)
