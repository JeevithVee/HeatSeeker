"""Agent 1 cross-review of Agent 3's evaluation: reproduce, then stress three assumptions."""
import sys, json, dataclasses, time
import numpy as np, pandas as pd
A3, INP, REPO = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, A3)
from core.evaluation import EvalConfig
from core.evaluation.run import evaluate_city_with_report

ALL = ("LANDSAT_5", "LANDSAT_7", "LANDSAT_8", "LANDSAT_9")
out = {}

def summarize(gold, cfg):
    ok = gold[(gold.n_pre_scenes >= cfg.min_pre_scenes) & (gold.n_post_scenes >= cfg.min_post_scenes)
              & (gold.n_controls >= cfg.min_controls) & gold.effect_k.notna()]
    e = ok.effect_k
    return dict(n=int(len(ok)), mean=round(float(e.mean()), 4), site_se=round(float(e.std(ddof=1) / np.sqrt(len(e))), 4),
                median=round(float(e.median()), 4), detected=int((ok.quality_label == "detected").sum()))

def block(report, key="overall"):
    g = (report.get("pooled_block_sensitivity") or report.get("pooled_sensitivity") or {}).get("grids", [])
    return [(x["block_size_m"], x["origin_offset_fraction"], x[key].get("mean_effect_k"), x[key].get("se_k")) for x in g]

for city in ("nyc", "dc", "sea", "sf"):
    t0 = time.time()
    panel = pd.read_parquet(f"{INP}/{city}_panel.parquet")
    feats = pd.read_csv(f"{REPO}/ingest/us/samples/{city}_silver_features.csv")
    iv = pd.read_csv(f"{REPO}/ingest/us/samples/{city}_silver_interventions.csv")
    base = EvalConfig(n_bootstrap=60, n_placebo=300)
    res = {}

    # A. reproduce the published headline
    gold, rep = evaluate_city_with_report(panel, feats, iv, base, "all", "review")
    res["A_headline"] = summarize(gold, base)
    pub = pd.read_csv(f"{A3}/pipelines/site_effects/out/{city}_gold_site_effects.csv")
    pub = pub[pub.variant == "all"].set_index("site_id").effect_k
    mine = gold.set_index("site_id").effect_k
    both = pub.index.intersection(mine.index)
    res["A_vs_published"] = dict(n_pub=int(len(pub)), n_mine=int(len(mine)),
                                 max_abs_diff=float(np.nanmax(np.abs(pub[both] - mine[both]))))
    res["A_block_keys"] = [k for k in rep.keys()][:40]

    # B. in-time placebo: pretend the 2015-2019 plantings happened five years earlier and
    #    look only at data from before any of them existed (through 2014).
    yr = pd.to_datetime(panel.acquired_at_utc, utc=True).dt.year
    pre_panel = panel[yr <= 2014]
    fake = iv.assign(plant_year=iv.plant_year - 5)
    cfgB = dataclasses.replace(base, sensors=ALL, treatment_window=(2010, 2014))
    try:
        gB, rB = evaluate_city_with_report(pre_panel, feats, fake, cfgB, "all", "review")
        res["B_in_time_placebo"] = summarize(gB, cfgB)
        res["B_by_fake_year"] = {int(k): (int(len(v)), round(float(v.effect_k.mean()), 3)) for k, v in gB.dropna(subset=["effect_k"]).groupby("treatment_year")}
    except Exception as ex:
        res["B_in_time_placebo"] = f"FAILED {type(ex).__name__}: {ex}"

    # C. no matching on the pre-period outcome (regression-to-the-mean check)
    cfgC = dataclasses.replace(base, pretrend_weight=0.0)
    gC, _ = evaluate_city_with_report(panel, feats, iv, cfgC, "all", "review")
    res["C_no_pre_outcome_matching"] = summarize(gC, cfgC)

    # D. scale-free outcome: rel_k divided by each scene's spatial spread, rescaled to K
    p = panel.copy()
    med = p.groupby("scene_id").lst_median_k.transform("median")
    mad = p.groupby("scene_id").lst_median_k.transform(lambda s: (s - s.median()).abs().median())
    typical = float(p.drop_duplicates("scene_id").assign(m=mad).m.median())
    p["lst_median_k"] = med + (p.lst_median_k - med) / mad.clip(lower=0.2) * typical
    gD, _ = evaluate_city_with_report(p, feats, iv, base, "all", "review")
    res["D_scene_spread_normalised"] = summarize(gD, base)

    # E. scene composition: is the post period hotter than the pre period?
    usable = panel[(panel.city_clear_frac >= 0.5) & panel.sensor.isin(["LANDSAT_8", "LANDSAT_9"])].drop_duplicates("scene_id")
    uy = pd.to_datetime(usable.acquired_at_utc, utc=True)
    usable = usable[uy.dt.month.isin([6, 7, 8])].assign(y=uy.dt.year)
    res["E_tmax_c_pre2015_vs_2020plus"] = (round(float(usable[usable.y < 2015].tmax_c.mean()), 2), round(float(usable[usable.y >= 2020].tmax_c.mean()), 2),
                                           int((usable.y < 2015).sum()), int((usable.y >= 2020).sum()))
    res["secs"] = round(time.time() - t0, 1)
    out[city] = res
    print(city, json.dumps(res, indent=1, default=str), flush=True)
json.dump(out, open("review_out.json", "w"), indent=1, default=str)
