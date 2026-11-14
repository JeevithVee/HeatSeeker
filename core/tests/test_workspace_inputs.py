import hashlib
import json

import pandas as pd
import pytest
from unittest.mock import MagicMock

from pipelines.site_effects.run_site_effects import read_inputs


def test_file_inputs_require_matching_checksums_and_report_git_provenance(tmp_path):
    sources = {}
    for role in ("panel", "features", "interventions"):
        path = tmp_path / f"nyc_{role}.csv"
        pd.DataFrame({"country_code": ["US"], "city_id": ["nyc"], "site_id": ["cell"],
                      "scene_id": ["scene"]}).to_csv(path, index=False)
        sources[role] = {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "git_commit": "abc123"}
    (tmp_path / "manifest.json").write_text(json.dumps({"cities": {"nyc": sources}}))
    *_, version, provenance = read_inputs(None, "catalog", "nyc", str(tmp_path))
    assert version == "git:abc123"
    assert provenance["mode"] == "owner_provided_files"
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [{"version": 4}]
    panel = pd.read_csv(tmp_path / sources["panel"]["file"])
    spark.read.option.return_value.table.return_value.where.return_value.toPandas.return_value = panel
    *_, version, provenance = read_inputs(spark, "catalog", "nyc", str(tmp_path), "delta")
    assert version == "4"
    assert provenance["mode"] == "delta_panel_with_owner_feature_intervention_files"
    assert provenance["inputs"]["panel"]["delta_version"] == "4"
    spark.read.option.assert_called_once_with("versionAsOf", "4")
    (tmp_path / sources["panel"]["file"]).write_text("changed")
    with pytest.raises(ValueError, match="checksum"):
        read_inputs(None, "catalog", "nyc", str(tmp_path))


def test_delta_inputs_pin_each_version_before_reading():
    calls = []
    class Spark:
        @property
        def read(self):
            return self
        def sql(self, query):
            calls.append(("history", query))
            return self
        def collect(self):
            return [{"version": 7}]
        def option(self, key, value):
            calls.append(("option", key, value))
            return self
        def table(self, name):
            calls.append(("read", name))
            return self
        def where(self, where):
            return self
        def toPandas(self):
            return pd.DataFrame({"country_code": ["US"], "city_id": ["nyc"],
                                 "site_id": ["cell"], "scene_id": ["scene"]})
    *_, version, provenance = read_inputs(Spark(), "heatseeker", "nyc", "")
    assert version == "7"
    for i, role in enumerate(("panel", "features", "interventions")):
        assert calls[i * 3:i * 3 + 3] == [
            ("history", f"DESCRIBE HISTORY heatseeker.silver.{role} LIMIT 1"),
            ("option", "versionAsOf", "7"), ("read", f"heatseeker.silver.{role}")]
    assert provenance["mode"] == "delta_snapshots"
