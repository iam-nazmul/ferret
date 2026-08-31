"""Model IDs. Never write these strings at a call site (CLAUDE.md rule 3)."""

# Answers, and the offline eval judge.
ANSWER_MODEL = "claude-opus-5"
JUDGE_MODEL = "claude-opus-5"

# Cheap, high-volume: sufficiency grading, memory extraction, online sampled judging.
GRADE_MODEL = "claude-haiku-4-5"
EXTRACT_MODEL = "claude-haiku-4-5"

# Cost-reduction fallback. Last resort, and only after the eval gate (SPEC §16).
CHEAP_ANSWER_MODEL = "claude-sonnet-5"

# Effort levels (output_config.effort), by question shape.
EFFORT_SIMPLE = "low"
EFFORT_DEFAULT = "high"
EFFORT_SYNTHESIS = "xhigh"
