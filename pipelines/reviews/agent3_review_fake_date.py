"""Same-sensor fake-date test: Landsat 5 only, 2008-2011, every real 2015-2019 planting
pretended to happen in 2010. Pre = 2008-2009, post = 2011. No tree in the test existed yet."""
import sys, dataclasses, json
import numpy as np, pandas as pd
A3, INP, REPO = sys.argv[1:4]
sys.path.insert(0, A3)
from core.evaluation import EvalConfig
from core.evaluation.run import evaluate_city_with_report
for city in ("nyc", "dc", "sea", "sf"):
    panel = pd.read_parquet(f"{INP}/{city}_panel.parquet")
    yr = pd.to_datetime(panel.acquired_at_utc, utc=True).dt.year
    p = panel[(yr <= 2011) & (panel.sensor == "LANDSAT_5")]
    feats = pd.read_csv(f"{REPO}/ingest/us/samples/{city}_silver_features.csv")
    iv = pd.read_csv(f"{REPO}/ingest/us/samples/{city}_silver_interventions.csv")
    fake = iv.copy()
    w = fake.plant_year.between(2015, 2019)
    fake.loc[w, "plant_year"] = 2010
    fake.loc[~w, "plant_year"] = 2030          # still counts toward "ever planted" for controls
    for label, kw in (("published spec", {}), ("no pre-outcome matching", {"pretrend_weight": 0.0})):
        cfg = dataclasses.replace(EvalConfig(n_bootstrap=60, n_placebo=300), sensors=("LANDSAT_5",),
                                  treatment_window=(2010, 2010), **kw)
        try:
            g, rep = evaluate_city_with_report(p, feats, fake, cfg, "all", "review")
            ok = g[(g.n_pre_scenes >= 5) & (g.n_post_scenes >= 5) & (g.n_controls >= 3) & g.effect_k.notna()]
            grids = [(x["block_size_m"], x["origin_offset_fraction"], x["overall"].get("status"),
                      None if x["overall"].get("normal_interval_low_k") is None else
                      (round(x["overall"]["normal_interval_low_k"], 3), round(x["overall"]["normal_interval_high_k"], 3)))
                     for x in rep["pooled_block_sensitivity"].get("grids", [])]
            print(city, label, "scenes/yr", rep["scenes_per_year"], "n", len(ok), "mean", round(ok.effect_k.mean(), 3),
                  "site_se", round(ok.effect_k.std(ddof=1) / np.sqrt(max(len(ok), 1)), 3),
                  "detected", int((ok.quality_label == "detected").sum()), "placebo_mean", round(rep["placebo_mean_k"], 3), grids)
        except Exception as ex:
            print(city, label, "FAILED", type(ex).__name__, ex)
