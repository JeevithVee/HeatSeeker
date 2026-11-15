import sys, json
import numpy as np, pandas as pd, h3
A = sys.argv[1]
raw = pd.read_csv("data/bronze/nyc_tree_points/tree_points_raw.csv", dtype=str)
raw["dbh"] = pd.to_numeric(raw.DBH, errors="coerce")
raw["py"] = pd.to_numeric(raw.PlantedDate.str[:4], errors="coerce")
raw["cy"] = pd.to_numeric(raw.CreatedDate.str[:4], errors="coerce")
d = raw[raw.py.between(2015, 2026)]
print("NYC raw rows", len(raw), "dated 2015-2026", len(d))
# F1. replacement plantings: planting spaces that hold more than one tree-point record
per_space = raw.groupby("PlantingSpaceGlobalID").size()
d = d.assign(n_in_space=d.PlantingSpaceGlobalID.map(per_space))
print("F1. dated plantings whose planting space has another tree record:", f"{(d.n_in_space > 1).mean():.1%}", "| missing space id:", f"{d.PlantingSpaceGlobalID.isna().mean():.1%}")
others = raw[raw.PlantingSpaceGlobalID.isin(d.PlantingSpaceGlobalID.dropna())]
prev = others[others.py.isna() & others.TPStructure.isin(["Retired", "Stump", "Stump - Uprooted", "Shaft"])]
prev_big = prev.groupby("PlantingSpaceGlobalID").dbh.max()
d = d.assign(prev_dbh=d.PlantingSpaceGlobalID.map(prev_big))
w = d[d.py.between(2015, 2019)]
print(f"    2015-19 plantings: {len(w)}; in a space with an earlier removed/retired undated tree: {w.prev_dbh.notna().mean():.1%}; that earlier tree's median trunk diameter {w.prev_dbh.median():.0f} in, >=10 in: {(w.prev_dbh >= 10).sum()} ({(w.prev_dbh >= 10).mean():.1%} of plantings)")
# F2. size of planted trees today, by planting year
print("F2. trunk diameter today (in) by planting year, standing trees:")
st = d[d.TPStructure == "Full"]
print(st.groupby("py").dbh.describe()[["count", "50%", "75%", "max"]].round(1).to_string())
# F3. removal by planting year
rem = d.assign(removed=d.TPStructure.isin(["Retired", "Stump", "Stump - Uprooted", "Shaft"]) | (d.TPCondition == "Dead"))
print("F3. share of plantings now removed or dead, by planting year:", rem.groupby("py").removed.mean().round(3).to_dict())
# F4. undated young trees: plantings the date field does not capture
und = raw[raw.py.isna() & (raw.TPStructure == "Full")]
print(f"F4. undated standing trees: {len(und)}; trunk <=3 in: {(und.dbh <= 3).sum()}; of those, record created 2015 or later: {((und.dbh <= 3) & (und.cy >= 2015)).sum()}; created 2016+: {((und.dbh <= 3) & (und.cy >= 2016)).sum()}")
print("    undated standing trees by record-creation year:", und.groupby("cy").size().to_dict())
print("    dated plantings 2015 by month:", d[d.py == 2015].PlantedDate.str[5:7].value_counts().sort_index().to_dict())
# controls contaminated by undated young trees
xy = und[(und.dbh <= 3) & (und.cy >= 2016)].Geometry.str.extract(r"POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)")
cells = [h3.latlng_to_cell(float(b), float(a), 9) for a, b in zip(xy[0], xy[1])]
young = pd.Series(cells).value_counts()
iv = pd.read_csv(f"{A}/nyc_interventions.csv"); f = pd.read_csv(f"{A}/nyc_features.csv").set_index("site_id")
ever = iv.groupby("site_id").trees_planted.sum().reindex(f.index).fillna(0)
ctrl = f.index[(ever <= 2) & ~f.land_cover_class.isin(["open_water", "emergent_herbaceous_wetlands", "woody_wetlands"])]
yc = young.reindex(ctrl).fillna(0)
print(f"    control cells ({len(ctrl)}): with >=1 undated young tree recorded since 2016: {(yc >= 1).mean():.1%}; with >=3: {(yc >= 3).mean():.1%}; with >=10: {(yc >= 10).mean():.1%}")
# G2. spillover: controls next to treated cells, all cities
for city in ("nyc", "dc", "sea", "sf"):
    iv = pd.read_csv(f"{A}/{city}_interventions.csv"); f = pd.read_csv(f"{A}/{city}_features.csv").set_index("site_id")
    g = pd.read_csv(f"{A}/{city}_gold.csv"); treated = set(g.site_id)
    ever = iv.groupby("site_id").trees_planted.sum().reindex(f.index).fillna(0)
    planted_any = set(ever.index[ever > 2])
    ctrl = f.index[(ever <= 2) & ~f.land_cover_class.isin(["open_water", "emergent_herbaceous_wetlands", "woody_wetlands"])]
    adj_t = np.mean([any(n in treated for n in h3.grid_disk(c, 1) if n != c) for c in ctrl])
    adj_p = np.mean([any(n in planted_any for n in h3.grid_disk(c, 1) if n != c) for c in ctrl])
    print(f"G2. {city}: controls touching a treated cell {adj_t:.0%}; touching any cell with >2 dated trees {adj_p:.0%}")
