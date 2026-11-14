"""Leave-one-calendar-year-out jackknife of the pooled headline estimate. All sites share the
same scenes, so year-to-year swings in the treated-minus-control contrast are a common shock
that a spatial block jackknife cannot see."""
import sys
import numpy as np, pandas as pd
A3, INP, REPO = sys.argv[1:4]
sys.path.insert(0, A3)
from core.evaluation import EvalConfig
from core.evaluation.run import evaluate_city_with_report
cfg = EvalConfig(n_bootstrap=10, n_placebo=40)
def pooled(panel, feats, iv):
    g, _ = evaluate_city_with_report(panel, feats, iv, cfg, "all", "review")
    ok = g[(g.n_pre_scenes >= 5) & (g.n_post_scenes >= 5) & (g.n_controls >= 3) & g.effect_k.notna()]
    return float(ok.effect_k.mean()), len(ok)
for city in sys.argv[4:]:
    panel = pd.read_parquet(f"{INP}/{city}_panel.parquet")
    panel = panel[panel.sensor.isin(["LANDSAT_8", "LANDSAT_9"])]
    yr = pd.to_datetime(panel.acquired_at_utc, utc=True).dt.year
    feats = pd.read_csv(f"{REPO}/ingest/us/samples/{city}_silver_features.csv")
    iv = pd.read_csv(f"{REPO}/ingest/us/samples/{city}_silver_interventions.csv")
    point, n = pooled(panel, feats, iv)
    drops = {}
    for y in sorted(yr.unique()):
        try:
            drops[int(y)] = round(pooled(panel[yr != y], feats, iv)[0], 3)
        except Exception as ex:
            drops[int(y)] = None
    v = np.array([x for x in drops.values() if x is not None])
    m = len(v)
    se = float(np.sqrt((m - 1) / m * ((v - v.mean()) ** 2).sum()))
    print(city, "point", round(point, 3), "n", n, "year-jackknife se", round(se, 3),
          "interval", (round(point - 1.96 * se, 3), round(point + 1.96 * se, 3)), "leave-one-out", drops, flush=True)
