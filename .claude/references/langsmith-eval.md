# Reference — LangSmith evaluation API

Verified against LangChain docs, 2026-08. Used by `eval/`.

## Evaluator signature

LangSmith injects arguments **by parameter name**. Rename one and you get a confusing runtime error, not a type error.

```python
def correctness(inputs: dict, outputs: dict, reference_outputs: dict) -> bool: ...
def groundedness(inputs: dict, outputs: dict) -> bool: ...          # no reference needed
def citation_validity(outputs: dict) -> float: ...                  # outputs only
```

- `inputs` — the example's inputs
- `outputs` — what the target function returned
- `reference_outputs` — the example's expected outputs

Return a `bool`, a `float`, or an `EvaluationResult`-shaped dict (`{"key": ..., "score": ...}`) when you want to name the metric explicitly.

## Datasets

```python
from langsmith import Client

client = Client()
dataset = client.create_dataset("ferret-golden-qa")
client.create_examples(
    dataset_id=dataset.id,
    examples=[
        {"inputs": {"question": "..."},
         "outputs": {"answer": "...", "document_ids": ["..."]}},
    ],
)
```

## Running

```python
from langsmith import evaluate

results = evaluate(
    target_fn,                        # (inputs: dict) -> dict
    data="ferret-golden-qa",          # name or dataset object
    evaluators=[correctness, groundedness, retrieval_recall,
                citation_validity, refusal_accuracy],
    experiment_prefix="ferret-opus5-hybrid-rerank",
    max_concurrency=8,
    metadata={"models": ["claude-opus-5"], "retriever": "hybrid+bge-rerank",
              "chunk_tokens": 700, "top_k": 8},
)
```

`max_concurrency` runs the target in parallel — **the target must be concurrency-safe with distinct `thread_id`s per example**, or memory bleeds between examples and every number is garbage.

`metadata` populates the model/prompt/tool columns in the comparison UI. Put the parameters you're varying here; it's what makes experiments comparable months later.

## LLM-as-judge

Use structured output, and **put the explanation field before the verdict** — the model generates fields in declaration order, so reasoning first forces it to think before committing:

```python
from typing_extensions import Annotated, TypedDict

class CorrectnessGrade(TypedDict):
    explanation: Annotated[str, ..., "Reasoning for the score"]
    correct: Annotated[bool, ..., "True if correct relative to the reference"]

grader = init_chat_model("claude-opus-5").with_structured_output(CorrectnessGrade)
```

Prefer a deterministic evaluator wherever the property is checkable in code — free, fast, reproducible, and not arguable. Three of Ferret's five are.

## Tracing and feedback

```python
from langsmith import traceable

@traceable
def retrieve(...): ...

client.create_feedback(run_id, key="user_thumb", score=1, comment="...")
```

The `run_id` returned to the UI in the `done` SSE event must be the real LangSmith run id — the feedback endpoint uses it as the join key.

## Pitfalls

- An example with no expected `document_ids` makes `retrieval_recall` vacuously 1.0. `eval/sync.py` rejects those.
- Changing the judge model re-baselines every historical number. Treat it as a dataset change, not a code change.
- Each gate run costs real money. Don't wire it to a push-on-any-branch trigger.
