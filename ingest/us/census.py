"""US demographics and vulnerability inputs, fetched per county. No API key needed.

census_blocks  2020 Census blocks from TIGERweb: population and internal point.
               Blocks are much smaller than an H3 res-9 cell, so assigning each
               block's residents to the cell holding its internal point is a
               close allocation.
cdc_svi        CDC/ATSDR Social Vulnerability Index 2022, by 2020 census tract
               (ACS 2018-2022): share aged 65+, share below 150% of the
               poverty line, overall SVI percentile.

Median household income needs the Census Data API, which requires a key; it is
left null until a key is configured.
"""
import pandas as pd
import requests

from . import common

# Counties (state FIPS + county FIPS) that cover each city.
CITY_COUNTIES = {
    "nyc": ["36005", "36047", "36061", "36081", "36085"],
    "dc": ["11001"],
    "sf": ["06075"],
    "sea": ["53033"],
}

BLOCKS = {
    "source": "census_2020_blocks_tigerweb",
    "url": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/2/query",
    "license": "Public domain (US Census Bureau)",
    "fields": "GEOID,POP100,INTPTLAT,INTPTLON,AREALAND",
    "where": "STATE='{state}' AND COUNTY='{county}'",
    "order": "GEOID",
}
SVI = {
    "source": "cdc_svi_2022_tracts",
    "url": "https://onemap.cdc.gov/OneMapServices/rest/services/SVI/CDC_ATSDR_Social_Vulnerability_Index_2022_USA/FeatureServer/2/query",
    "license": "Public domain (CDC/ATSDR Social Vulnerability Index 2022)",
    "fields": "FIPS,E_TOTPOP,EP_AGE65,EP_POV150,RPL_THEMES",
    "where": "STCNTY='{state}{county}'",
    "order": "FIPS",
}
SVI_MISSING = -999


def _query_all(spec, county_fips, page_size=2000):
    """Page through an ArcGIS REST layer for one county; attributes only."""
    where = spec["where"].format(state=county_fips[:2], county=county_fips[2:])
    rows, offset = [], 0
    while True:
        r = requests.get(spec["url"], timeout=180, params={
            "where": where, "outFields": spec["fields"], "returnGeometry": "false",
            "orderByFields": spec["order"], "resultOffset": offset,
            "resultRecordCount": page_size, "f": "json",
        })
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            raise RuntimeError(f"{spec['source']} {county_fips}: {body['error']}")
        page = [f["attributes"] for f in body["features"]]
        rows.extend(page)
        if not page or not body.get("exceededTransferLimit"):
            return rows
        offset += len(page)


def fetch(spec, city_id):
    """All rows for a city's counties, as received."""
    rows = []
    for county in CITY_COUNTIES[city_id]:
        rows.extend(_query_all(spec, county))
    return pd.DataFrame(rows)


def blocks_to_bronze(raw, city_id, ingested_at=None):
    lat = raw["INTPTLAT"].astype(float)
    lon = raw["INTPTLON"].astype(float)
    return common.bronze_frame(
        raw, city_id=city_id, role="demographics", source=BLOCKS["source"],
        license=BLOCKS["license"], value=raw["POP100"].astype(float), units="persons",
        date="2020-04-01",
        geometry="POINT(" + lon.astype(str) + " " + lat.astype(str) + ")",
        source_record_id=raw["GEOID"], ingested_at=ingested_at,
    )


def svi_to_bronze(raw, city_id, ingested_at=None):
    return common.bronze_frame(
        raw, city_id=city_id, role="vulnerability", source=SVI["source"],
        license=SVI["license"], value=raw["RPL_THEMES"].astype(float), units="percentile",
        date="2022", geometry=None,
        source_record_id=raw["FIPS"], ingested_at=ingested_at,
    )


def block_population(raw_blocks, raw_svi):
    """One row per block: location, residents, and its tract's vulnerability shares.

    Shares are fractions 0-1; tracts where SVI has no estimate get NaN.
    """
    blocks = pd.DataFrame({
        "block_id": raw_blocks["GEOID"].astype(str),
        "lat": raw_blocks["INTPTLAT"].astype(float),
        "lon": raw_blocks["INTPTLON"].astype(float),
        "population": raw_blocks["POP100"].astype(float),
    })
    blocks["tract_id"] = blocks["block_id"].str[:11]

    tracts = pd.DataFrame({
        "tract_id": raw_svi["FIPS"].astype(str),
        "share_age_65_plus": raw_svi["EP_AGE65"].astype(float),
        "share_low_income": raw_svi["EP_POV150"].astype(float),
    })
    for col in ("share_age_65_plus", "share_low_income"):
        tracts[col] = tracts[col].where(tracts[col] != SVI_MISSING) / 100.0
    return blocks.merge(tracts, on="tract_id", how="left")
