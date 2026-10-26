"""Week 6: plain-text LLM calls (used to rewrite reply drafts).

The classifier has its own JSON-only calls in app/classifier/llm.py. This module is the
same idea for free text. Callers MUST pass already-masked text and MUST handle None
(meaning "use the template instead").
"""

from __future__ import annotations

import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


def llm_available(settings: Settings) -> bool:
    if settings.llm_provider == "anthropic":
        return bool(settings.anthropic_api_key)
    if settings.llm_provider == "gemini":
        return bool(settings.gemini_api_key)
    return False


def model_name(settings: Settings) -> str | None:
    if settings.llm_provider == "anthropic":
        return settings.anthropic_model
    if settings.llm_provider == "gemini":
        return settings.gemini_model
    return None


def generate_text(system: str, user: str, settings: Settings, max_tokens: int = 800) -> str | None:
    """Return the model's reply text, or None on any problem (no key, timeout, refusal...)."""
    if not llm_available(settings):
        return None
    try:
        if settings.llm_provider == "anthropic":
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key,
                                         timeout=settings.llm_timeout_seconds, max_retries=1)
            response = client.messages.create(
                model=settings.anthropic_model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}],
            )
            if response.stop_reason == "refusal":
                return None
            return "".join(b.text for b in response.content if b.type == "text").strip() or None

        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"{settings.gemini_model}:generateContent")
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens},
        }
        response = httpx.post(url, json=body, headers={"x-goog-api-key": settings.gemini_api_key},
                              timeout=settings.llm_timeout_seconds)
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip() or None
    except Exception as exc:  # noqa: BLE001 - any failure means "use the template"
        logger.warning("LLM text generation failed (%s); using template", type(exc).__name__)
        return None
