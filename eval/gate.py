"""Gate thresholds and the pass/fail decision."""

from dataclasses import dataclass

# SPEC §13.3 — keep in sync with eval/README.md and .claude/skills/eval-gate.
THRESHOLDS: dict[str, tuple[float, float]] = {
    # metric: (minimum, max_drop_vs_main)
    "correctness": (0.85, 0.02),
    "groundedness": (0.95, 0.01),
    "retrieval_recall": (0.90, 0.02),
    "citation_validity": (0.99, 0.0),
    "refusal_accuracy": (0.90, 0.03),
}

LATENCY_P95_MS = 6000
LATENCY_MAX_INCREASE = 0.15


@dataclass
class GateResult:
    passed: bool
    failures: list[str]
    rows: list[tuple[str, float | None, float, str]]

    def render(self) -> str:
        lines = ["### Eval gate", "", "| metric | main | this PR | Δ |", "|---|---|---|---|"]
        for name, baseline, current, delta in self.rows:
            base = f"{baseline:.2f}" if baseline is not None else "—"
            lines.append(f"| {name} | {base} | {current:.2f} | {delta} |")
        if self.failures:
            lines += ["", "**FAILED:**"] + [f"- {f}" for f in self.failures]
        return "\n".join(lines)


def evaluate_gate(
    scores: dict[str, float],
    baseline: dict[str, float] | None = None,
    p95_ms: float | None = None,
    baseline_p95_ms: float | None = None,
) -> GateResult:
    baseline = baseline or {}
    failures: list[str] = []
    rows: list[tuple[str, float | None, float, str]] = []

    for metric, (minimum, max_drop) in THRESHOLDS.items():
        current = scores.get(metric)
        if current is None:
            failures.append(f"{metric}: not measured")
            continue

        base = baseline.get(metric)
        delta = f"{current - base:+.2f}" if base is not None else "—"
        rows.append((metric, base, current, delta))

        if current < minimum:
            failures.append(f"{metric}: {current:.3f} below minimum {minimum}")
        if base is not None and (base - current) > max_drop:
            failures.append(
                f"{metric}: dropped {base - current:.3f} vs main (max {max_drop})"
            )

    if p95_ms is not None:
        delta = "—"
        if baseline_p95_ms:
            increase = (p95_ms - baseline_p95_ms) / baseline_p95_ms
            delta = f"{increase:+.0%}"
            if increase > LATENCY_MAX_INCREASE:
                failures.append(f"p95 latency up {increase:.0%} (max {LATENCY_MAX_INCREASE:.0%})")
        rows.append(("p95 latency (ms)", baseline_p95_ms, p95_ms, delta))
        if p95_ms > LATENCY_P95_MS:
            failures.append(f"p95 latency {p95_ms:.0f}ms above {LATENCY_P95_MS}ms")

    return GateResult(passed=not failures, failures=failures, rows=rows)
