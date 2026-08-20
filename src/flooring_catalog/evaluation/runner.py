"""Run transparent deterministic graders over recommendation rankings."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from flooring_catalog.evaluation.models import (
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationCheck,
    EvaluationCorpus,
    EvaluationReport,
)
from flooring_catalog.ranking import FlooringRecommendationRanker


def load_evaluation_corpus(path: str | Path) -> EvaluationCorpus:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"evaluation corpus not found: {source}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"evaluation corpus is not valid JSON: {source}") from error
    try:
        return EvaluationCorpus.model_validate(value)
    except ValidationError as error:
        raise ValueError(f"invalid evaluation corpus: {error}") from error


def _evaluate_case(
    case: EvaluationCase,
    ranker: FlooringRecommendationRanker,
) -> EvaluationCaseResult:
    ranked = ranker.rank(
        [candidate.to_hybrid_candidate() for candidate in case.candidates],
        case.preferences,
    )
    ranked_skus = tuple(item.candidate.product.sku for item in ranked)
    top_sku = ranked_skus[0] if ranked_skus else None
    checks = (
        EvaluationCheck(
            name="acceptable_top_result",
            passed=top_sku in case.acceptable_top_skus,
            details=f"top={top_sku!r}; acceptable={list(case.acceptable_top_skus)!r}",
        ),
        EvaluationCheck(
            name="required_products_retrieved",
            passed=set(case.required_skus).issubset(ranked_skus),
            details=f"required={list(case.required_skus)!r}; ranked={list(ranked_skus)!r}",
        ),
        EvaluationCheck(
            name="forbidden_products_excluded",
            passed=set(case.forbidden_skus).isdisjoint(ranked_skus),
            details=f"forbidden={list(case.forbidden_skus)!r}; ranked={list(ranked_skus)!r}",
        ),
        EvaluationCheck(
            name="explanations_present",
            passed=all(
                component.reasons
                for item in ranked
                for component in item.score.components
            ),
            details="every ranked score component must include a deterministic reason",
        ),
    )
    passed_checks = sum(check.passed for check in checks)
    score = passed_checks / len(checks)
    return EvaluationCaseResult(
        case_id=case.case_id,
        ranked_skus=ranked_skus,
        score=score,
        passed=passed_checks == len(checks),
        checks=checks,
    )


def evaluate_corpus(
    corpus: EvaluationCorpus,
    *,
    ranker: FlooringRecommendationRanker | None = None,
) -> EvaluationReport:
    service = ranker or FlooringRecommendationRanker()
    results = tuple(_evaluate_case(case, service) for case in corpus.cases)
    passed_cases = sum(result.passed for result in results)
    total_cases = len(results)
    return EvaluationReport(
        corpus_name=corpus.name,
        corpus_version=corpus.version,
        passed_cases=passed_cases,
        total_cases=total_cases,
        pass_rate=passed_cases / total_cases,
        mean_case_score=sum(result.score for result in results) / total_cases,
        results=results,
    )
