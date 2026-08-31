"""Sufficiency grading — are the retrieved chunks enough to answer the question?"""

GRADE_PROMPT = """You are grading retrieved document excerpts for sufficiency.

Given a QUESTION and EXCERPTS, decide whether the excerpts contain enough information
to answer the question completely and accurately.

Return sufficient=true only if a careful reader could answer the question from these
excerpts alone. Return sufficient=false if the excerpts are merely topically related,
cover only part of the question, or would require outside knowledge to connect.

Being strict here is correct. A false "sufficient" produces a confidently wrong answer;
a false "insufficient" costs one retrieval retry."""
