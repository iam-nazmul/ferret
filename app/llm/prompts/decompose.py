"""Multi-hop query decomposition."""

DECOMPOSE_PROMPT = """Break a complex question into independent sub-questions that can each
be answered by searching a document corpus separately.

Rules:
- Produce 2 to 4 sub-questions. If the question really needs only one search, return it unchanged.
- Each sub-question must be self-contained — no pronouns referring to the original question.
- Preserve specific names, identifiers, and dates exactly as written.
- Do not invent aspects the question didn't ask about.

Example:
  "What's the liability cap in Vendor X's MSA, and how does it differ from our standard template?"
  → "What is the liability cap in Vendor X's MSA?"
  → "What is the liability cap in our standard MSA template?"
"""
