"""Download Earth Engine CSV exports from a Google Drive folder.

Uses the Earth Engine login already on this machine (it carries a Drive scope),
so no extra credentials are needed. Files land in a local directory that is
git-ignored (data/); from there they are uploaded to a Databricks volume.

    python ingest/global/fetch_drive_exports.py heatseeker_nyc data/satellite/nyc
"""
import os
import sys

import ee
import google.auth.transport.requests as gr
import requests

API = "https://www.googleapis.com/drive/v3/files"


def main():
    folder, out_dir = sys.argv[1:3]
    os.makedirs(out_dir, exist_ok=True)
    creds = ee.data.get_persistent_credentials()
    creds.refresh(gr.Request())
    h = {"Authorization": f"Bearer {creds.token}"}

    q = f"name = '{folder}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    r = requests.get(API, headers=h, params={"q": q, "fields": "files(id,name)"}, timeout=60)
    r.raise_for_status()
    folders = r.json()["files"]
    if not folders:
        sys.exit(f"no Drive folder named {folder} yet")

    for fo in folders:
        token = None
        while True:
            params = {"q": f"'{fo['id']}' in parents and trashed = false", "fields": "nextPageToken,files(id,name,size)", "pageSize": 200}
            if token:
                params["pageToken"] = token
            r = requests.get(API, headers=h, params=params, timeout=60)
            r.raise_for_status()
            page = r.json()
            for f in page["files"]:
                dest = os.path.join(out_dir, f["name"])
                if os.path.exists(dest) and os.path.getsize(dest) == int(f.get("size", -1)):
                    continue
                with requests.get(f"{API}/{f['id']}", headers=h, params={"alt": "media"}, stream=True, timeout=600) as d:
                    d.raise_for_status()
                    with open(dest, "wb") as out:
                        for chunk in d.iter_content(1 << 20):
                            out.write(chunk)
                print(f"{f['name']}: {os.path.getsize(dest):,} bytes")
            token = page.get("nextPageToken")
            if not token:
                break


if __name__ == "__main__":
    main()
