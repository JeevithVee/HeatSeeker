import sys, json
import numpy as np, pandas as pd
A, P = sys.argv[1], sys.argv[2]
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
WATER = ("open_water", "emergent_herbaceous_wetlands", "woody_wetlands")
for city in ("nyc", "dc", "sea", "sf"):
    f = pd.read_csv(f"{A}/{city}_features.csv").set_index("site_id")
    iv = pd.read_csv(f"{A}/{city}_interventions.csv")
    g = pd.read_csv(f"{A}/{city}_gold.csv"); g = g[g.variant == "all"]
    p = pd.read_parquet(f"{P}/{city}_panel.parquet")
    t = pd.to_datetime(p.acquired_at_utc, utc=True)
    p = p.assign(y=t.dt.year, m=t.dt.month, hour=t.dt.hour + t.dt.minute / 60)
    u = p[p.sensor.isin(["LANDSAT_8", "LANDSAT_9"]) & p.m.isin([6, 7, 8]) & (p.city_clear_frac >= 0.5) & (p.valid_pixel_frac >= 0.7)].copy()
    u["rel"] = u.lst_median_k - u.groupby("scene_id").lst_median_k.transform("median")
    print(f"\n================ {city.upper()} ================")
    # --- A. dose and signal size
    w = iv[iv.plant_year.between(2015, 2019)].groupby("site_id").trees_planted.sum()
    ever = iv.groupby("site_id").trees_planted.sum()
    treated = g.site_id
    dose = w.reindex(treated)
    area_m2 = f.area_km2.mean() * 1e6
    print(f"A. cell area {area_m2/1e4:.1f} ha. treated cells {len(treated)}: dose 2015-19 median {dose.median():.0f}, p90 {dose.quantile(.9):.0f}, max {dose.max():.0f} trees"
          f" = median {dose.median()/(area_m2/1e4):.1f} trees/ha")
    for crown in (10, 25, 50):
        print(f"   if each tree now shades {crown} m2: median canopy gain {dose.median()*crown/area_m2*100:.2f}% of cell, p90 {dose.quantile(.9)*crown/area_m2*100:.2f}%")
    # empirical LST sensitivity to canopy, from our own tables
    cell = u.groupby("site_id").rel.mean().rename("rel").to_frame().join(f[["canopy_frac_latest", "impervious_frac", "land_cover_class", "population", "existing_tree_count", "canopy_frac_baseline", "elevation_m"]]).dropna()
    land = cell[~cell.land_cover_class.isin(WATER)]
    X = np.column_stack([np.ones(len(land)), land.canopy_frac_latest, land.impervious_frac])
    b = np.linalg.lstsq(X, land.rel.to_numpy(), rcond=None)[0]
    b1 = np.polyfit(land.canopy_frac_latest, land.rel, 1)[0]
    print(f"   our own data, across cells: surface temp vs canopy fraction: {b1:.1f} K per 100% canopy alone; {b[1]:.1f} K per 100% canopy holding impervious fixed (impervious {b[2]:+.1f})")
    for crown in (10, 25, 50):
        gain = dose.median() * crown / area_m2
        print(f"   => expected cooling of the median treated cell at {crown} m2/tree: {b1*gain:+.3f} K (canopy-only slope), {b[1]*gain:+.3f} K (holding impervious)")
    # --- D. noise
    cm = u.groupby("site_id").rel.transform("mean")
    u["dev"] = u.rel - cm
    sd_scene = u.groupby("site_id").dev.std().median()
    ym = u.groupby(["site_id", "y"]).rel.mean().unstack()
    sd_year = ym.sub(ym.mean(axis=1), axis=0).std(axis=1).median()
    print(f"D. noise: one cell's scene-to-scene SD around its own mean {sd_scene:.2f} K; SD of its yearly means {sd_year:.2f} K; median MDE in gold {g.mde_k.median():.2f} K")
    # --- E. scenes
    sc = u.drop_duplicates("scene_id")
    per_year = sc.groupby("y").size()
    print(f"E. usable Landsat 8/9 summer scenes: {len(sc)}; per year {per_year.to_dict()}")
    print(f"   pre-2015 scenes: {int(per_year[per_year.index < 2015].sum())}; overpass hour UTC {sc.hour.min():.1f}-{sc.hour.max():.1f}; tmax on scene days {sc.tmax_c.min():.0f}-{sc.tmax_c.max():.0f} C")
    print(f"   clear rows: LST median {u.lst_median_k.median()-273.15:.1f} C; rows colder than 15 C: {(u.lst_median_k < 288.15).sum()} ; rel < -15 K: {(u.rel < -15).sum()}; scenes per cell median {u.groupby('site_id').size().median():.0f}, min {u.groupby('site_id').size().min()}")
    # --- B. did measured canopy move with planting?
    f2 = f[~f.land_cover_class.isin(WATER)].copy()
    f2["dose"] = w.reindex(f2.index).fillna(0); f2["ever"] = ever.reindex(f2.index).fillna(0)
    f2["dcan"] = f2.canopy_frac_latest - f2.canopy_frac_baseline
    bins = pd.cut(f2.dose, [-1, 0, 4, 9, 19, 29, 1e9], labels=["0", "1-4", "5-9", "10-19", "20-29", "30+"])
    tab = f2.groupby(bins, observed=True).agg(cells=("dcan", "size"), canopy_2014=("canopy_frac_baseline", "mean"), canopy_change=("dcan", "mean"), impervious=("impervious_frac", "mean"), inventory_trees=("existing_tree_count", "mean"), pop=("population", "mean"))
    print("B. measured canopy change 2014->2024 by trees planted 2015-19 (non-water cells):"); print(tab.round(4).to_string())
    print(f"   correlation(dose, canopy change) = {f2.dose.corr(f2.dcan):+.3f}; citywide canopy change {f2.dcan.mean():+.4f}")
    # --- C. does the canopy product see street trees?
    dev = f2[f2.land_cover_class.str.startswith("developed")]
    print(f"C. developed cells: corr(inventory trees, canopy_frac) = {dev.existing_tree_count.corr(dev.canopy_frac_latest):+.2f}; cells with >=150 inventory trees: {(dev.existing_tree_count>=150).sum()}, of which canopy < 5%: {((dev.existing_tree_count>=150)&(dev.canopy_frac_latest<0.05)).sum()}, canopy < 10%: {((dev.existing_tree_count>=150)&(dev.canopy_frac_latest<0.10)).sum()}")
    # --- G/H. controls
    ctrl = f2[f2.ever <= 2]
    trt = f2.loc[f2.index.intersection(treated)]
    print(f"G. controls (<=2 dated trees ever, non-water): {len(ctrl)}; with zero residents {(ctrl.population==0).mean():.0%}; mean inventory trees {ctrl.existing_tree_count.mean():.0f} vs treated {trt.existing_tree_count.mean():.0f}; impervious {ctrl.impervious_frac.mean():.2f} vs {trt.impervious_frac.mean():.2f}; canopy {ctrl.canopy_frac_baseline.mean():.2f} vs {trt.canopy_frac_baseline.mean():.2f}")
    res = f2[(f2.population > 0) & f2.land_cover_class.str.startswith("developed")]
    print(f"H. populated developed cells: {len(res)}; with any dated planting {(res.ever>0).mean():.0%}; with <=2 ever {(res.ever<=2).sum()}; treated cells' trees planted AFTER 2019: median {iv[iv.plant_year>2019].groupby('site_id').trees_planted.sum().reindex(treated).fillna(0).median():.0f} (vs dose {dose.median():.0f})")
    # --- I/J. timing and mortality
    wi = iv[iv.plant_year.between(2015, 2019)]
    fm = pd.to_datetime(wi.first_plant_date).dt.month
    print(f"I. 2015-19 cell-years by month of first planting: Oct-Dec {(fm>=10).mean():.0%}, Jan-May {(fm<=5).mean():.0%}, Jun-Sep {((fm>=6)&(fm<=9)).mean():.0%}")
    print(f"J. removal_tracked={iv.removal_tracked.iloc[0]}; of 2015-19 plantings, recorded removed/dead: {wi.trees_removed.sum()/wi.trees_planted.sum():.1%}")
