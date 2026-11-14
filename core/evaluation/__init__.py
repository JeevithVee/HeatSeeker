"""Evaluation engine ("Prove"): did a planted H3 cell cool relative to matched unplanted cells?

Inputs are pandas DataFrames in the frozen silver schemas (see /schema). Output is a
DataFrame in the gold.site_effects schema. Pure pandas/numpy; no Spark, no H3, no
country-specific code. Heavy runs happen in /pipelines on Databricks.
"""

from core.evaluation.config import EvalConfig
from core.evaluation.run import (
    evaluate_city,
    evaluate_city_all_variants,
    evaluate_city_all_variants_with_reports,
    evaluate_city_with_report,
)

METHOD_VERSION = "0.3.0"   # 0.3: controls exclude planting across the full record, not only 2015-2019

__all__ = [
    "EvalConfig", "evaluate_city", "evaluate_city_all_variants", "evaluate_city_with_report",
    "evaluate_city_all_variants_with_reports", "METHOD_VERSION",
]
