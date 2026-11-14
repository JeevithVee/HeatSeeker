"""Upload the Earth Engine CSV exports to a Unity Catalog volume.

The silver.panel job (build_silver_panel.py) reads them from there. Sign-in is
the Databricks browser login; no token is stored in the repo.

    python pipelines/panel/upload_exports.py https://<workspace-host> data/satellite
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import VolumeType

CATALOG, SCHEMA, VOLUME = "heatseeker", "bronze", "landing"
DEST = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/satellite"


def main():
    host, local_root = sys.argv[1], Path(sys.argv[2])
    w = WorkspaceClient(host=host, auth_type="external-browser")
    if VOLUME not in [v.name for v in w.volumes.list(CATALOG, SCHEMA)]:
        w.volumes.create(catalog_name=CATALOG, schema_name=SCHEMA, name=VOLUME, volume_type=VolumeType.MANAGED)
    files = sorted(local_root.glob("*/*.csv"))

    def put(path):
        with open(path, "rb") as f:
            w.files.upload(f"{DEST}/{path.name}", f, overwrite=True)
        return path.name

    with ThreadPoolExecutor(4) as pool:
        done = list(pool.map(put, files))
    remote = {e.name: e.file_size for e in w.files.list_directory_contents(DEST)}
    mismatched = [p.name for p in files if remote.get(p.name) != p.stat().st_size]
    print(f"uploaded {len(done)} files to {DEST}; size mismatches: {mismatched}")


if __name__ == "__main__":
    main()
