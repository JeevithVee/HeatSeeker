"""Protect the city replacement boundary and CLI output contract without a workspace."""

import csv
import json
from types import SimpleNamespace

import pytest

from pipelines.site_effects.load_gold import SQL_TYPES, Warehouse, load, validate_csv
from core.evaluation.run import GOLD_COLUMNS


@pytest.fixture
def gold_csv(tmp_path):
    path = tmp_path / "gold.csv"
    row = dict.fromkeys(SQL_TYPES, "")
    row.update(country_code="US", city_id="nyc", site_id="892a1000067ffff", variant="all",
               quality_label="inconclusive", event_study_json=json.dumps({"-1": 0.2, "5": -0.1}))
    def write(rows):
        with path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=SQL_TYPES)
            writer.writeheader()
            writer.writerows(rows)
        return path
    return write, row


def test_csv_contract_and_embedded_json(gold_csv):
    write, row = gold_csv
    assert list(SQL_TYPES) == GOLD_COLUMNS
    assert validate_csv(write([row]), "nyc") == 1


@pytest.mark.parametrize("case", ["empty", "duplicate", "wrong_city", "bad_json"])
def test_invalid_input_fails_before_upload(gold_csv, case):
    write, row = gold_csv
    rows = [row]
    if case == "empty":
        rows = []
    elif case == "duplicate":
        rows *= 2
    elif case == "wrong_city":
        row["city_id"] = "dc"
    else:
        row["event_study_json"] = "{broken"
    class NoNetwork:
        def command(self, *args, **kwargs):
            pytest.fail("Invalid input must fail before a CLI call")
    with pytest.raises(ValueError):
        load(NoNetwork(), write(rows), "nyc", "heatseeker")


def test_source_validation_failure_preserves_target(gold_csv):
    write, row = gold_csv
    class BadSource:
        def command(self, *args, **kwargs):
            pass
        def sql(self, statement):
            assert statement.startswith("SELECT COUNT(*)")
            return [["1", "0", "1"]]  # embedded JSON did not survive SQL CSV parsing
    with pytest.raises(RuntimeError, match="SQL validation"):
        load(BadSource(), write([row]), "nyc", "heatseeker")


def test_cli_requests_json_and_reports_sql_error(monkeypatch):
    def run(cmd, **kwargs):
        assert cmd[-2:] == ["-o", "json"]
        return SimpleNamespace(stdout=json.dumps({"status": {"state": "FAILED", "error": {
            "message": "CSV parse failed"}}}))
    monkeypatch.setattr("subprocess.run", run)
    with pytest.raises(RuntimeError, match="CSV parse failed"):
        Warehouse("test", "warehouse").sql("SELECT 1")


def test_load_replaces_city_in_one_statement(gold_csv):
    write, row = gold_csv
    statements = []
    class FakeWarehouse:
        def command(self, *args, **kwargs):
            pass
        def sql(self, statement):
            statements.append(statement)
            if statement.startswith("SELECT COUNT(*)"):
                if "read_files" in statement:
                    assert "escape => '\"'" in statement
                    return [["1", "0", "0"]]
                return [["1", "1", "0"]]
            if statement.startswith("DESCRIBE"):
                return [[key, value, None] for key, value in SQL_TYPES.items()]
            if statement.startswith("WITH incoming"):
                return [["0", "0"]]
            return []
    load(FakeWarehouse(), write([row]), "nyc", "heatseeker")
    writes = [s for s in statements if s.startswith(("INSERT", "DELETE"))]
    assert len(writes) == 1
    assert "REPLACE WHERE city_id = 'nyc'" in writes[0]
