"""HeatSeeker app: Recommend / Track / Results.

Streamlit app structured to run as a Databricks App. All numbers shown come
from the gold/silver tables (shared rule 12); units and labels come from
/config/us (shared rule 10). Storage is Kelvin per the frozen schema;
display defaults to Fahrenheit per config (temperature differences:
dF = dK x 1.8).

Visual system: the validated reference palette from the dataviz method -
sequential blue for magnitude ramps, fixed status colors for quality labels
(always paired with a text chip, never color alone), categorical blue vs
muted gray for the site-vs-controls series, documented inks and hairlines.
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
CITIES = {c["city_id"]: c for c in CONFIG["cities"]}
FAHRENHEIT = CONFIG["display"]["temperature_unit"] == "fahrenheit"
UNIT = "°F" if FAHRENHEIT else "°C"
HEADLINE_VARIANT = "all"

# ---- palette ----
# Brand: HeatSeeker green-white-amber (validated: contrast + CVD separation;
# spec page "HeatSeeker Palette"). Green acts, amber highlights as a fill
# with ink text only (darkening amber merges with green for protanopia).
BRAND = "#1a7d3a"        # green-600: primary / interactive
BRAND_HOVER = "#1c6531"  # green-700
BRAND_DEEP = "#18391f"   # green-900: headings
WASH = "#f2f9f2"         # green-50
ACCENT = "#f0a726"       # amber-400: highlight fills, always ink text
ACCENT_SOFT = "#fad6a5"  # amber-200
# Data-layer colors (validated reference instance; see dataviz skill) are a
# separate system and stay as they are:
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
SURFACE = "#fcfcfb"
PLANE = "#f9f9f7"
HAIRLINE = "#e1e0d9"
SERIES_BLUE = "#2a78d6"
# sequential blue anchors, light -> dark (steps 100/250/400/550/700)
SEQ_BLUE = [(205, 226, 251), (134, 182, 239), (57, 135, 229),
            (28, 92, 171), (13, 54, 107)]
STATUS = {  # fixed status palette; chips carry the label, color never alone
    "detected cooling": ("#0ca30c", (12, 163, 12)),
    "detected warming": ("#d03b3b", (208, 59, 59)),
    "inconclusive": ("#fab219", (250, 178, 25)),
    "not_detectable": ("#898781", (137, 135, 129)),
}

CAVEAT = (
    "**Surface temperature is not felt (air) temperature** — effects here are "
    "satellite-measured land surface temperature at the late-morning overpass. "
    "Reliable cooling is not established: sensitivity intervals span zero, "
    "NYC's pooled cooling is indistinguishable from zero under alternative "
    "specifications, and Seattle shows a negative association, not a causal "
    "estimate. All four cities are temperate; results are untested in hot, "
    "dry climates."
)

CSS = f"""
<style>
#MainMenu, footer {{visibility: hidden;}}
.block-container {{padding-top: 2.2rem; max-width: 1200px;}}
h1 {{font-size: 1.9rem; letter-spacing: -0.02em; margin-bottom: 0;
    color: {BRAND_DEEP};}}
h1::after {{content: ""; display: block; width: 64px; height: 4px;
    border-radius: 2px; margin-top: 6px;
    background: linear-gradient(90deg, {BRAND} 0 42px, {ACCENT} 42px);}}
h3 {{color: {BRAND_DEEP};}}
a {{color: {BRAND_HOVER};}}
/* sidebar wears the brand wash */
[data-testid="stSidebar"] {{
  background: {WASH}; border-right: 1px solid {HAIRLINE};
}}
[data-testid="stSidebar"] [data-testid="stAlert"] {{
  background: #fdead0; border-left: 3px solid {ACCENT};
  border-radius: 0 8px 8px 0; color: {INK};
}}
[data-testid="stSidebar"] [data-testid="stAlert"] * {{color: {INK_2};}}
/* interactive chrome is green (works with or without the theme file) */
button[kind="primary"], [data-testid="stFormSubmitButton"] button {{
  background: {BRAND}; color: #fff; border: 0;
}}
button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] button:hover {{
  background: {BRAND_HOVER}; color: #fff;
}}
[data-testid="stSlider"] [role="slider"] {{background: {BRAND};}}
[data-baseweb="tag"] {{background: #e0f3e2; color: {BRAND_DEEP};}}
[data-baseweb="tag"] span {{color: {BRAND_DEEP};}}
input[type="checkbox"], [data-testid="stCheckbox"] span {{accent-color: {BRAND};}}
hr {{border-color: {HAIRLINE};}}
[data-testid="stMetric"] {{
  background: {SURFACE}; border: 1px solid rgba(11,11,11,0.10);
  border-top: 3px solid {BRAND}; border-radius: 12px; padding: 0.8rem 1rem;
}}
[data-testid="stMetricValue"] {{
  font-variant-numeric: tabular-nums; font-size: 1.45rem;
}}
[data-testid="stMetricLabel"] {{color: {INK_2};}}
[data-testid="stMetricDelta"] svg {{display: none;}}
[data-testid="stCaptionContainer"] {{color: {INK_2};}}
.hs-chip {{
  display: inline-block; padding: 1px 10px 2px; margin-right: 6px;
  border-radius: 999px; background: {SURFACE};
  border: 1px solid {HAIRLINE}; color: {INK_2}; font-size: 0.82rem;
}}
.hs-dot {{
  display: inline-block; width: 9px; height: 9px; border-radius: 50%;
  margin-right: 5px; vertical-align: baseline;
}}
.hs-note {{
  border-left: 3px solid {ACCENT}; background: {WASH};
  border-radius: 0 8px 8px 0; padding: 8px 12px; color: {INK_2};
  font-size: 0.86rem; margin: 6px 0 2px;
}}
.hs-badge {{
  display: inline-block; background: {ACCENT}; color: {INK};
  border-radius: 999px; padding: 1px 10px 2px; font-size: 0.8rem;
  font-weight: 600;
}}
</style>
"""


def dk(kelvin_delta):
    """Convert a temperature *difference* to display units (dF = dK x 1.8)."""
    return kelvin_delta * 1.8 if FAHRENHEIT else kelvin_delta


def seq_ramp(q: np.ndarray) -> np.ndarray:
    """Percentile [0,1] -> RGB along the sequential blue ramp."""
    q = np.clip(np.asarray(q, dtype=float), 0, 1) * (len(SEQ_BLUE) - 1)
    lo = np.floor(q).astype(int)
    hi = np.minimum(lo + 1, len(SEQ_BLUE) - 1)
    frac = (q - lo)[:, None]
    anchors = np.array(SEQ_BLUE, dtype=float)
    return anchors[lo] * (1 - frac) + anchors[hi] * frac


def chips(items: list[tuple[str, str]]) -> None:
    """Legend chips: (hex, label) pairs - text always beside the color."""
    html = " ".join(
        f'<span class="hs-chip"><span class="hs-dot" '
        f'style="background:{hexv}"></span>{label}</span>'
        for hexv, label in items)
    st.markdown(html, unsafe_allow_html=True)


@st.cache_data(ttl=300)
def tables():
    t = {name: data.load_table(name) for name in data.TABLES}
    eff = t["site_effects"]
    if not eff.empty and "variant" in eff.columns:
        t["site_effects"] = eff[eff["variant"] == HEADLINE_VARIANT]
    return t


def deck_map(df: pd.DataFrame, colors: np.ndarray, radius: int = 120,
             tooltip_cols: list[str] | None = None) -> None:
    d = df.copy()
    d[["r", "g", "b"]] = np.asarray(colors, dtype=int)
    tip = None
    if tooltip_cols:
        tip = {"text": "\n".join(f"{c}: {{{c}}}" for c in tooltip_cols)}
    center = CITIES[st.session_state["city_id"]]["center"]
    st.pydeck_chart(pdk.Deck(
        map_style="light",
        initial_view_state=pdk.ViewState(
            latitude=center["lat"], longitude=center["lon"], zoom=10.3),
        layers=[pdk.Layer(
            "ScatterplotLayer", d,
            get_position=["centroid_lon", "centroid_lat"],
            get_fill_color=["r", "g", "b", 185],
            get_radius=radius, pickable=bool(tip),
            stroked=True, get_line_color=[255, 255, 255, 90], line_width_min_pixels=0.5,
        )],
        tooltip=tip,
    ))


def themed(chart: alt.Chart) -> alt.Chart:
    return (chart
            .configure(background="transparent", font="system-ui")
            .configure_axis(gridColor=HAIRLINE, domainColor="#c3c2b7",
                            labelColor=MUTED, titleColor=INK_2,
                            labelFontSize=11, titleFontSize=12)
            .configure_legend(labelColor=INK_2, titleColor=INK_2)
            .configure_view(stroke=None))


# ---------------------------------------------------------------- Recommend

def view_recommend(t):
    recs, feats = t["recommendations"], t["features"]
    if recs.empty:
        st.warning("No recommendations yet — run the Learn + Plan pipeline.")
        return

    st.subheader("Where to plant next")
    st.caption("Ranked by predicted cooling × vulnerable residents ÷ cost. "
               "Every 5th site is held out unplanted as a future control. "
               "Predicted coolings are model estimates trained on measured "
               "effects and inherit their limitations — they are not "
               "guarantees.")

    c1, c2, c3 = st.columns(3)
    top_n = c1.slider("Show top N sites", 25, len(recs), min(150, len(recs)),
                      step=25)
    kinds = c2.multiselect("Intervention", sorted(recs["suggested_intervention"].unique()),
                           default=sorted(recs["suggested_intervention"].unique()))
    show_holdout = c3.checkbox("Include holdout controls", value=True)

    d = recs.merge(feats[["site_id", "centroid_lat", "centroid_lon",
                          "canopy_frac_baseline", "impervious_frac", "population"]],
                   on="site_id")
    d = d[d["suggested_intervention"].isin(kinds)]
    if not show_holdout:
        d = d[~d["holdout_control"]]
    d = d.nsmallest(top_n, "rank").copy()

    q = d["score"].rank(pct=True).to_numpy()
    d["cooling_15y"] = dk(d["predicted_cooling_k_15y"]).round(2)
    deck_map(d, seq_ramp(q), tooltip_cols=["site_id", "rank", "cooling_15y",
                                           "suggested_intervention"])
    chips([("#cde2fb", "lower priority"), ("#3987e5", "mid"),
           ("#0d366b", "top priority")])

    site = st.selectbox("Site detail", d.sort_values("rank")["site_id"])
    r = d[d["site_id"] == site].iloc[0]

    m = st.columns(5)
    m[0].metric("Rank", int(r["rank"]))
    m[1].metric(f"Predicted cooling at 15y ({UNIT})",
                f"{dk(r['predicted_cooling_k_15y']):.2f}",
                f"range {dk(r['predicted_cooling_k_15y_low']):.2f} to "
                f"{dk(r['predicted_cooling_k_15y_high']):.2f}", delta_color="off")
    m[2].metric("Vulnerable residents", f"{r['vulnerable_residents']:,.0f}")
    m[3].metric("Est. cost", f"${r['est_cost_usd']:,.0f}")
    m[4].metric("Suggestion", r["suggested_intervention"].replace("_", " "))
    st.markdown(
        f'<div class="hs-note">Why: canopy {r["canopy_frac_baseline"]:.0%}, '
        f'impervious {r["impervious_frac"]:.0%}, population '
        f'{r["population"]:,.0f}. Cooling at 5y: '
        f'{dk(r["predicted_cooling_k_5y"]):.2f} {UNIT} (trees still maturing).'
        + (f' <span class="hs-badge" style="background:{ACCENT_SOFT}">'
           'Holdout control — do not plant</span>'
           if r["holdout_control"] else "") + "</div>",
        unsafe_allow_html=True)

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
        d = inter.merge(feats[["site_id", "centroid_lat", "centroid_lon"]],
                        on="site_id")
        q = d["trees_planted"].rank(pct=True).to_numpy()
        deck_map(d, seq_ramp(q),
                 tooltip_cols=["site_id", "trees_planted", "plant_year"])
        chips([("#cde2fb", "few trees"), ("#3987e5", "some"),
               ("#0d366b", "many trees")])
        c = st.columns(4)
        c[0].metric("Cell-years planted", f"{len(d):,}")
        c[1].metric("Trees planted", f"{d['trees_planted'].sum():,.0f}")
        c[2].metric("Trees surviving", f"{d['trees_surviving'].sum():,.0f}")
        c[3].metric("Years", f"{d['plant_year'].min()}–{d['plant_year'].max()}")

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
            try:
                logged_by = st.context.headers.get("X-Forwarded-Email") or "local"
            except Exception:
                logged_by = "local"
            dest = data.log_planting({
                "country_code": "US", "city_id": st.session_state["city_id"],
                "site_id": site,
                "intervention_type": kind, "trees_planted": int(n),
                "planted_date": str(when), "cost_usd": float(cost),
                "logged_by": logged_by,
                "logged_at_utc": datetime.now(timezone.utc).isoformat(),
            })
            st.success(f"Logged {n} × {kind} at {site} → {dest}. Recorded as "
                       "staging: it becomes eligible for evaluation after it "
                       "is confirmed into the city's planting records and "
                       "enough post-planting scenes arrive.")

    new = data.load_new_plantings()
    if not new.empty:
        st.dataframe(new, width="stretch", hide_index=True)


# ----------------------------------------------------------------- Results

def view_results(t):
    eff, feats, panel = t["site_effects"], t["features"], t["panel_sample"]
    if eff.empty:
        st.warning("No measured effects yet — waiting on gold.site_effects.")
        return

    st.subheader("Did past plantings cool anything?")
    eff = eff.copy()
    eff["outcome"] = np.where(
        eff["quality_label"] == "detected",
        np.where(eff["effect_k"] < 0, "detected cooling", "detected warming"),
        eff["quality_label"])
    det_cooling = eff[eff["outcome"] == "detected cooling"]
    det_warming = eff[eff["outcome"] == "detected warming"]

    m = st.columns(4)
    m[0].metric("Sites evaluated", f"{len(eff):,}")
    m[1].metric("Detected (cooling / warming)",
                f"{len(det_cooling)} / {len(det_warming)}",
                help="Unadjusted statistical label, not proof that planting "
                     "caused the change.")
    m[2].metric("Inconclusive or not detectable",
                f"{len(eff) - len(det_cooling) - len(det_warming):,}",
                help="Honestly reported: effects too small to see at 30 m "
                     "resolution are the norm, not a failure.")
    med = dk(det_cooling["effect_k"].median()) if len(det_cooling) else float("nan")
    m[3].metric(f"Median detected cooling ({UNIT})", f"{med:.2f}")

    present = [o for o in STATUS if o in set(eff["outcome"])]
    labels = st.multiselect("Outcome", present, default=present)
    d = eff[eff["outcome"].isin(labels)].merge(
        feats[["site_id", "centroid_lat", "centroid_lon"]], on="site_id")
    d["effect_display"] = dk(d["effect_k"]).round(2)
    deck_map(d, np.array([STATUS[o][1] for o in d["outcome"]]),
             tooltip_cols=["site_id", "effect_display", "outcome"])
    chips([(STATUS[o][0], o.replace("_", " ")) for o in present])

    cost_per_site = CONFIG["costs_usd"]["street_trees"]
    if len(det_cooling):
        total_cooling = dk(-det_cooling["effect_k"].sum())
        st.markdown(
            f'<div class="hs-note">Portfolio: {total_cooling:.1f} {UNIT} of '
            f'detected cooling across {len(det_cooling)} sites ≈ '
            f'{total_cooling / (len(det_cooling) * cost_per_site) * 10000:.2f} '
            f'{UNIT} per $10k (at ~${cost_per_site:,} per planted cell, config '
            'estimate). Detected-site sums overstate the portfolio: most '
            'evaluated sites are inconclusive.</div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("**Site detail — before / after vs matched controls**")
    site = st.selectbox("Evaluated site", d["site_id"])
    r = eff[eff["site_id"] == site].iloc[0]

    m = st.columns(5)
    m[0].metric(f"Measured effect ({UNIT})", f"{dk(r['effect_k']):.2f}",
                f"CI {dk(r['ci_low_k']):.2f} to {dk(r['ci_high_k']):.2f}",
                delta_color="off")
    m[1].metric("Label", r["outcome"].replace("_", " "),
                help=f"Minimum detectable effect at this site: "
                     f"{dk(r['mde_k']):.2f} {UNIT}; placebo p = "
                     f"{r['placebo_p']:.2f}. A statistical label, not causal "
                     "proof.")
    m[2].metric("Planted", int(r["treatment_year"]))
    m[3].metric("Scenes pre / post", f"{r['n_pre_scenes']} / {r['n_post_scenes']}")
    m[4].metric("Matched controls", int(r["n_controls"]))

    p = panel[panel["site_id"] == site] if not panel.empty else panel
    if not p.empty:
        long = p.melt(
            id_vars=["scene_date", "post"],
            value_vars=["site_temp_rel_k", "control_temp_rel_k"],
            var_name="series", value_name="temp_rel_k",
        )
        long["series"] = long["series"].map(
            {"site_temp_rel_k": "this site",
             "control_temp_rel_k": "control pool"})
        long["temp_rel"] = dk(long["temp_rel_k"])
        plant_date = p.loc[p["post"], "scene_date"].min()
        chart = alt.Chart(long).mark_line(
            point=alt.OverlayMarkDef(size=26), strokeWidth=2,
        ).encode(
            x=alt.X("scene_date:T", title="clear-sky summer scene"),
            y=alt.Y("temp_rel:Q",
                    title=f"surface temp vs city baseline ({UNIT})"),
            color=alt.Color("series:N", title=None,
                            scale=alt.Scale(domain=["this site", "control pool"],
                                            range=[SERIES_BLUE, MUTED])),
        )
        rule = alt.Chart(pd.DataFrame({"d": [plant_date]})).mark_rule(
            strokeDash=[4, 4], color=INK_2).encode(x="d:T")
        st.altair_chart(themed(chart + rule), width="stretch")
        st.caption("Dashed line: planting year. If the blue line drops below "
                   "gray after it, the site cooled relative to its control "
                   "pool. The effect estimate above uses matched controls, "
                   "not this pooled view.")


# -------------------------------------------------------------------- main

st.markdown(CSS, unsafe_allow_html=True)
st.title("🌳 HeatSeeker")
st.caption("Plan, plant, prove — urban cooling for US cities")

t = tables()
available = [c for c in CITIES
             if c in set(t["features"].get("city_id", pd.Series()).unique())]
city_id = st.sidebar.selectbox(
    "City", available or list(CITIES),
    format_func=lambda c: CITIES[c]["name"])
st.session_state["city_id"] = city_id
view = st.sidebar.radio("View", ["Recommend", "Track", "Results"])
st.sidebar.divider()
st.sidebar.caption(f"Data: {data.source()} "
                   f"({'Unity Catalog tables' if data.source() == 'live' else 'verified snapshot of the tables'})")
st.sidebar.info(CAVEAT)

t = {k: (v[v["city_id"] == city_id] if "city_id" in v.columns else v)
     for k, v in t.items()}
{"Recommend": view_recommend, "Track": view_track, "Results": view_results}[view](t)

st.divider()
st.caption(CAVEAT)
