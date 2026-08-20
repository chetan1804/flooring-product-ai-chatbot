from __future__ import annotations

import json

import pytest

from flooring_catalog.evaluation import evaluate_corpus, load_evaluation_corpus
from flooring_catalog.evaluation_cli import main


def test_bundled_recommendation_corpus_passes() -> None:
    report = evaluate_corpus(load_evaluation_corpus("evals/recommendation_cases.json"))
    assert report.total_cases == 5
    assert report.passed_cases == 5
    assert report.pass_rate == 1
    assert all(result.passed for result in report.results)


def test_invalid_evaluation_expectations_are_rejected(tmp_path) -> None:
    corpus = {
        "name": "invalid",
        "version": "1",
        "cases": [
            {
                "case_id": "unknown_sku",
                "description": "Invalid expected product",
                "preferences": {},
                "candidates": [
                    {"sku": "A", "retrieval_score": 0.5},
                    {"sku": "B", "retrieval_score": 0.5},
                ],
                "acceptable_top_skus": ["MISSING"],
            }
        ],
    }
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(corpus), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown SKUs"):
        load_evaluation_corpus(path)


def test_evaluation_cli_writes_machine_readable_report(tmp_path) -> None:
    output = tmp_path / "report.json"
    exit_code = main(
        [
            "--corpus",
            "evals/recommendation_cases.json",
            "--output",
            str(output),
        ]
    )
    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["pass_rate"] == 1
