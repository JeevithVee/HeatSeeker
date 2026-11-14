"""Deploy the HeatSeeker app as a Databricks App.

    python app/deploy.py [--host https://...] [--app-name heatseeker]

What it does:
1. Uploads app source (app/, config/us/config.yaml) to the workspace.
2. Uploads the demo/data_real snapshot to /Volumes/heatseeker/gold/files/app_snapshot.
3. Creates the app if missing, grants its service principal read access to
   the catalog/schema/volume, and deploys.

The deployed app reads the volume snapshot (HEATSEEKER_DATA_DIR in app.yaml).
Swapping app/data.py to live SQL against heatseeker.gold.* is the follow-up;
the snapshot IS the sanctioned fallback either way.
"""

from __future__ import annotations

import argparse
import io
import time
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.apps import App, AppDeployment
from databricks.sdk.service.sql import StatementState
from databricks.sdk.service.workspace import ImportFormat

REPO = Path(__file__).resolve().parents[1]
VOLUME_DATA = "/Volumes/heatseeker/gold/files/app_snapshot"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="https://dbc-f8d41fd5-0183.cloud.databricks.com")
    ap.add_argument("--app-name", default="heatseeker")
    ap.add_argument("--warehouse-id", default="b646c232444bafe7")
    ap.add_argument("--snapshot", default=str(REPO / "demo" / "data_real"))
    args = ap.parse_args()

    w = WorkspaceClient(host=args.host, auth_type="external-browser")
    me = w.current_user.me().user_name
    src_root = f"/Workspace/Users/{me}/heatseeker-app"

    # 1. source upload
    uploads = {
        f"{src_root}/app/app.py": REPO / "app" / "app.py",
        f"{src_root}/app/data.py": REPO / "app" / "data.py",
        f"{src_root}/app/app.yaml": REPO / "app" / "app.yaml",
        f"{src_root}/app/requirements.txt": REPO / "app" / "requirements.txt",
        f"{src_root}/app/.streamlit/config.toml":
            REPO / "app" / ".streamlit" / "config.toml",
        # Inside the app dir: the deployment bundles ONLY source_code_path,
        # so the config must live within it.
        f"{src_root}/app/config/us/config.yaml":
            REPO / "config" / "us" / "config.yaml",
    }
    w.workspace.mkdirs(f"{src_root}/app/.streamlit")
    w.workspace.mkdirs(f"{src_root}/app/config/us")
    for dest, src in uploads.items():
        w.workspace.upload(dest, io.BytesIO(src.read_bytes()),
                           format=ImportFormat.AUTO, overwrite=True)
    print(f"source -> {src_root}")

    # 2. data snapshot into the app's own source tree (readable by the app's
    # service principal with no catalog grants; app.yaml points
    # HEATSEEKER_DATA_DIR at it)
    w.workspace.mkdirs(f"{src_root}/app/data")
    for p in sorted(Path(args.snapshot).glob("*.parquet")):
        w.workspace.upload(f"{src_root}/app/data/{p.name}",
                           io.BytesIO(p.read_bytes()),
                           format=ImportFormat.RAW, overwrite=True)
        print(f"data   -> {src_root}/app/data/{p.name}")

    # 3. app create (idempotent) + grants + deploy
    try:
        app = w.apps.get(args.app_name)
        print(f"app {args.app_name} exists ({app.compute_status.state})")
    except Exception:
        print(f"creating app {args.app_name} (takes a few minutes)...")
        app = w.apps.create_and_wait(app=App(
            name=args.app_name,
            description="HeatSeeker: plan, plant, prove urban cooling"))

    # Grants are only needed once the app queries heatseeker.* live; they
    # require MANAGE on the catalog (its owner), so failures are non-fatal.
    sp = app.service_principal_client_id
    def sql(stmt):
        r = w.statement_execution.execute_statement(
            statement=stmt, warehouse_id=args.warehouse_id, wait_timeout="50s")
        while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
            time.sleep(3)
            r = w.statement_execution.get_statement(r.statement_id)
        assert r.status.state == StatementState.SUCCEEDED, r.status

    for stmt in (
        f"GRANT USE CATALOG ON CATALOG heatseeker TO `{sp}`",
        f"GRANT USE SCHEMA ON SCHEMA heatseeker.gold TO `{sp}`",
        f"GRANT SELECT ON SCHEMA heatseeker.gold TO `{sp}`",
        f"GRANT READ VOLUME ON VOLUME heatseeker.gold.files TO `{sp}`",
    ):
        try:
            sql(stmt)
        except AssertionError as e:
            print(f"grant skipped (needs catalog owner): {stmt}")
    print(f"app service principal: {sp}")

    dep = w.apps.deploy_and_wait(
        app_name=args.app_name,
        app_deployment=AppDeployment(source_code_path=f"{src_root}/app"))
    print("deployment:", dep.status.state)
    print("URL:", w.apps.get(args.app_name).url)


if __name__ == "__main__":
    main()
