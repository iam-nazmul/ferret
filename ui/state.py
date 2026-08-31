"""Session state keys in one place — they're stringly-typed and easy to typo into a silent bug."""

MESSAGES = "messages"
THREAD_ID = "thread_id"
TOKEN = "auth_token"
FILTERS = "filters"
SELECTED_SOURCE = "selected_source"
PAGE = "page"

EXAMPLE_QUESTIONS = [
    "How many days is the refund window on the Enterprise plan?",
    "What is the deployment approval process?",
    "What does our standard MSA say about liability caps?",
    "What have recent reports said about churn?",
]
