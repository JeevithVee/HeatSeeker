"""Deploy an immutable, code-only workspace snapshot and the evaluation job.

No credentials or personal paths are copied. Input files are staged separately.
Only resets a job with this component's name and tags. Uses the local CLI login.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.site_effects.load_gold import Warehouse, identifier


def source_files():
    return sorted([ROOT / "core/__init__.py", *ROOT.glob("core/evaluation/*.py"),
                   *ROOT.glob("core/tests/*.py"),
                   *[ROOT / "pipelines/site_effects" / name for name in
                     ("run_site_effects.py", "run_tests.py", "load_gold.py")]])


def deploy(profile, catalog, input_dir, receipt_path, panel_source="files"):
    identifier(catalog)
    cli = Warehouse(profile)
    files = source_files()
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode() + b"\0" + path.read_bytes())
    source_hash = digest.hexdigest()
    target = f"/Shared/heatseeker/agent3/{source_hash[:16]}"
    with tempfile.TemporaryDirectory(prefix="heatseeker-agent3-code-") as tmp:
        stage = Path(tmp)
        for path in files:
            dest = stage / path.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
        (stage / "source_snapshot.json").write_text(json.dumps({"source_sha256": source_hash}))
        print(f"[deploy] uploading {len(files)} code files to {target}", flush=True)
        cli.command("workspace", "import-dir", str(stage), target, "--overwrite")

    job = json.loads((ROOT / "pipelines/site_effects/job.json").read_text())
    job.pop("git_source", None)
    for task in job["tasks"]:
        script = task["spark_python_task"]
        script["source"] = "WORKSPACE"
        script["python_file"] = f"/Workspace{target}/{script['python_file']}"
    for parameter in job["parameters"]:
        if parameter["name"] == "input_dir":
            parameter["default"] = input_dir
        elif parameter["name"] == "catalog":
            parameter["default"] = catalog
        elif parameter["name"] == "panel_source":
            parameter["default"] = panel_source
        elif parameter["name"] == "output_dir":
            parameter["default"] = f"/Volumes/{catalog}/gold/files/site_effects/runs"
    job["tags"]["source_hash"] = source_hash[:16]
    existing = [item for item in cli.command("jobs", "list", json_output=True)
                if item.get("settings", {}).get("name") == job["name"]]
    if len(existing) > 1:
        raise RuntimeError("Multiple jobs have this name; refusing an ambiguous reset")
    if existing:
        item = existing[0]
        if item["settings"].get("tags", {}).get("component") != "site_effects":
            raise RuntimeError("Matching job is not tagged as this component; refusing to reset")
        job_id = item["job_id"]
        cli.command("jobs", "reset", "--json", json.dumps({"job_id": job_id, "new_settings": job}))
    else:
        job_id = cli.command("jobs", "create", "--json", json.dumps(job), json_output=True)["job_id"]
    receipt = {"job_id": job_id, "source_sha256": source_hash, "workspace_source_root": target,
               "input_dir": input_dir, "panel_source": panel_source, "job_name": job["name"]}
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2), flush=True)
    return receipt


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default="heatseeker")
    ap.add_argument("--catalog", default="heatseeker")
    ap.add_argument("--input-dir", default="")
    ap.add_argument("--panel-source", choices=("files", "delta"), default="files")
    ap.add_argument("--receipt", type=Path, default=Path("/private/tmp/heatseeker-agent3-deployment.json"))
    args = ap.parse_args()
    try:
        deploy(args.profile, args.catalog, args.input_dir, args.receipt, args.panel_source)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.stderr.strip() or exc.stdout.strip() or str(exc)) from exc


if __name__ == "__main__":
    main()
