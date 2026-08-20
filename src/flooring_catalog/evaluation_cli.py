"""Command-line runner for deterministic recommendation evaluations."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from flooring_catalog.evaluation import evaluate_corpus, load_evaluation_corpus

DEFAULT_CORPUS = Path("evals/recommendation_cases.json")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate recommendation ranking quality")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--minimum-pass-rate", type=float, default=1.0)
    args = parser.parse_args(argv)
    if not 0 <= args.minimum_pass_rate <= 1:
        parser.error("--minimum-pass-rate must be between 0 and 1")

    report = evaluate_corpus(load_evaluation_corpus(args.corpus))
    serialized = json.dumps(report.model_dump(mode="json"), indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if report.pass_rate >= args.minimum_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
