"""Long-term memory extraction.

The exclusion list is a security property, not a style preference: the memory store is
keyed by user with no ACL join, so document content landing there escapes the permission
model. See app/memory/README.md.
"""

EXTRACT_PROMPT = """Extract durable facts about the USER from this conversation turn.

Extract:
- their role, team, or function
- projects, vendors, or systems they work on
- stated preferences about how they want answers (format, length, level of detail)
- topics they return to repeatedly

Never extract:
- the contents of documents, or any fact the assistant retrieved rather than the user stated
- personal or sensitive details the user did not state directly about themselves
- one-off task context that won't matter next week

Return an empty list when nothing durable was said. That is the common case — most turns
contain no lasting fact, and inventing one pollutes the profile."""
