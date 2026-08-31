"""Push eval/datasets/*.jsonl to LangSmith. Idempotent — re-running does not duplicate."""

import json
from pathlib import Path

DATASETS_DIR = Path(__file__).parent / "datasets"


def load_dataset(path: Path) -> list[dict]:
    examples = []
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            example = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_no}: {exc}") from exc
        validate_example(example, f"{path.name}:{line_no}")
        examples.append(example)
    return examples


def validate_example(example: dict, where: str) -> None:
    if "inputs" not in example or "question" not in example["inputs"]:
        raise ValueError(f"{where}: missing inputs.question")

    outputs = example.get("outputs") or {}
    should_refuse = outputs.get("should_refuse", False)

    # An example with no expected document_ids makes retrieval_recall vacuously 1.0.
    if not should_refuse and not outputs.get("document_ids"):
        raise ValueError(
            f"{where}: non-refusal examples must list expected document_ids, "
            "otherwise retrieval_recall is meaningless"
        )


def sync(dataset_name: str | None = None) -> dict[str, int]:
    from langsmith import Client

    client = Client()
    results: dict[str, int] = {}

    for path in sorted(DATASETS_DIR.glob("*.jsonl")):
        name = f"ferret-{path.stem}"
        if dataset_name and name != dataset_name:
            continue

        examples = load_dataset(path)
        try:
            dataset = client.read_dataset(dataset_name=name)
        except Exception:
            dataset = client.create_dataset(name)

        existing = {
            json.dumps(e.inputs, sort_keys=True) for e in client.list_examples(dataset_id=dataset.id)
        }
        new = [
            e for e in examples if json.dumps(e["inputs"], sort_keys=True) not in existing
        ]
        if new:
            client.create_examples(
                dataset_id=dataset.id,
                examples=[{"inputs": e["inputs"], "outputs": e.get("outputs", {})} for e in new],
            )
        results[name] = len(new)
        print(f"{name}: {len(new)} new, {len(examples)} total")

    return results


if __name__ == "__main__":
    import sys

    sync(sys.argv[1] if len(sys.argv) > 1 else None)
