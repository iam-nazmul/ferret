"""Eval runner.

    python -m eval.run_eval --dataset ferret-golden-qa
    python -m eval.run_eval --gate

Every run that exercises the model costs real money. The gate is ~$4 and ~6 minutes.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

from eval.evaluators import ALL_EVALUATORS
from eval.gate import evaluate_gate
from eval.target import make_target

BASELINE_PATH = Path(__file__).parent / "baseline.json"
GATE_DATASETS = ["ferret-golden-qa", "ferret-refusal"]


def run(dataset: str, limit: int | None = None, prefix: str = "ferret") -> dict:
    from langsmith import evaluate

    results = evaluate(
        make_target(),
        data=dataset,
        evaluators=ALL_EVALUATORS,
        experiment_prefix=prefix,
        max_concurrency=8,
        metadata=_experiment_metadata(),
    )
    return _aggregate(results)


def _experiment_metadata() -> dict:
    from app.config import settings
    from app.llm.models import ANSWER_MODEL

    return {
        "models": [ANSWER_MODEL],
        "retriever": "hybrid+rrf+bge-rerank",
        "chunk_tokens": settings.chunk_tokens,
        "top_k": settings.top_k,
        "rrf_k": settings.rrf_k,
        "embedding_dims": settings.embedding_dims,
    }


def _aggregate(results) -> dict:
    scores: dict[str, list[float]] = {}
    latencies: list[float] = []

    for row in results:
        for res in row.get("evaluation_results", {}).get("results", []):
            if res.score is not None:
                scores.setdefault(res.key, []).append(float(res.score))
        run = row.get("run")
        if run is not None and getattr(run, "start_time", None) and getattr(run, "end_time", None):
            latencies.append((run.end_time - run.start_time).total_seconds() * 1000)

    aggregated = {k: statistics.mean(v) for k, v in scores.items() if v}
    if latencies:
        latencies.sort()
        idx = max(0, int(len(latencies) * 0.95) - 1)
        aggregated["_p95_ms"] = latencies[idx]
    return aggregated


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Ferret evaluation")
    parser.add_argument("--dataset", help="a single dataset to run")
    parser.add_argument("--limit", type=int, help="cap examples (iteration only, not the gate)")
    parser.add_argument("--gate", action="store_true", help="run the CI regression gate")
    parser.add_argument("--save-baseline", action="store_true", help="record these as main's numbers")
    args = parser.parse_args()

    if not args.gate and not args.dataset:
        parser.error("pass --dataset or --gate")

    if args.dataset:
        scores = run(args.dataset, args.limit)
        print(json.dumps(scores, indent=2))
        return 0

    combined: dict[str, float] = {}
    p95 = 0.0
    for dataset in GATE_DATASETS:
        print(f"\n=== {dataset} ===", file=sys.stderr)
        scores = run(dataset, prefix="ferret-gate")
        p95 = max(p95, scores.pop("_p95_ms", 0.0))
        for k, v in scores.items():
            combined[k] = (combined[k] + v) / 2 if k in combined else v

    baseline = {}
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text())

    result = evaluate_gate(
        combined,
        baseline=baseline.get("scores"),
        p95_ms=p95,
        baseline_p95_ms=baseline.get("p95_ms"),
    )
    print("\n" + result.render())

    if args.save_baseline:
        BASELINE_PATH.write_text(json.dumps({"scores": combined, "p95_ms": p95}, indent=2))
        print(f"\nbaseline written to {BASELINE_PATH}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
