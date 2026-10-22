"""Message classifier: rules (offline), optional LLM, and safety guardrails.

Use `classify_message()` from app.classifier.service. It is the only entry point.
"""

from app.classifier.service import classify_message

__all__ = ["classify_message"]
