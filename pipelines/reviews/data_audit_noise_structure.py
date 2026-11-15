import sys
import numpy as np, pandas as pd, h3
A, P = sys.argv[1], sys.argv[2]
for city in ("nyc", "dc", "sea", "sf"):
    f = pd.read_csv(f"{A}/{city}_features.csv").set_index("site_id")
    iv = pd.read_csv(f"{A}/{city}_interventions.csv")
    p = pd.read_parquet(f"{P}/{city}_panel.parquet")
    t = pd.to_datetime(p.acquired_at_utc, utc=True)
    u = p[p.sensor.isin(["LANDSAT_8", "LANDSAT_9"]) & t.dt.month.isin([6, 7, 8]) & (p.city_clear_frac >= 0.5) & (p.valid_pixel_frac >= 0.7)].copy()
    u["rel"] = u.lst_median_k - u.groupby("scene_id").lst_median_k.transform("median")
    wide = u.pivot(index="site_id", columns="scene_id", values="rel")
    dev = wide.sub(wide.mean(axis=1), axis=0)
    # spatial structure of the noise: a cell's scene anomaly vs the mean anomaly of its six neighbours
    idx = set(dev.index); rs = []
    sample = dev.sample(min(600, len(dev)), random_state=0)
    for sid, row in sample.iterrows():
        nb = [n for n in h3.grid_disk(sid, 1) if n != sid and n in idx]
        if len(nb) >= 4:
            m = dev.loc[nb].mean()
            ok = row.notna() & m.notna()
            if ok.sum() >= 20: rs.append(np.corrcoef(row[ok], m[ok])[0, 1])
    far = []
    ids = list(dev.index); rng = np.random.default_rng(0)
    for sid, row in sample.iloc[:300].iterrows():
        o = dev.loc[rng.choice(ids)]
        ok = row.notna() & o.notna()
        if ok.sum() >= 20: far.append(np.corrcoef(row[ok], o[ok])[0, 1])
    print(f"{city}: scene anomaly correlation with its neighbours {np.median(rs):.2f} (random other cell {np.median(far):.2f}); valid pixels per clear cell median {u.valid_pixel_count.median():.0f}; within-cell pixel SD median {u.lst_std_k.median():.2f} K")
    # how the contrast between planted-type and control-type cells swings year to year
    w = iv[iv.plant_year.between(2015, 2019)].groupby("site_id").trees_planted.sum()
    ever = iv.groupby("site_id").trees_planted.sum()
    yr = pd.to_datetime(u.drop_duplicates("scene_id").set_index("scene_id").acquired_at_utc, utc=True).dt.year
    hi = wide.index.intersection(w.index[w >= 10]); lo = wide.index.difference(ever.index[ever > 2])
    gap = (wide.loc[hi].mean() - wide.loc[lo].mean())
    by = gap.groupby(yr.reindex(gap.index)).mean()
    print(f"   planted-minus-control gap in surface temp, scene by scene: mean {gap.mean():+.2f} K, SD across scenes {gap.std():.2f} K; yearly means range {by.min():+.2f} to {by.max():+.2f} K (SD {by.std():.2f})")
    for thr in (30, 60, 100):
        print(f"   cells with >= {thr} trees planted 2015-19: {(w >= thr).sum()}", end=";")
    print()
    # cells large shares water / edge
    print(f"   cells in grid {len(f)}; dominated by water/wetland {(f.land_cover_class.isin(['open_water','emergent_herbaceous_wetlands','woody_wetlands'])).sum()}; cells never clear enough to use {len(f) - wide.shape[0]}")
