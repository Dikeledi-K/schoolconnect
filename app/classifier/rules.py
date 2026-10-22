"""Offline, rule-based classifier. Works with no API key and no internet.

Three steps, all driven by app/taxonomy.py:
1. Category: count keyword matches per category; the highest score wins.
2. Language: count common "marker" words per language.
3. Urgency: deadline words raise it, relaxed words lower it.

Safety keywords are also detected here (find_safety_terms), but the decision
to raise urgency is made by the guardrails in service.py, so that the same
guardrails also check LLM answers.
"""

from __future__ import annotations

import re
from functools import lru_cache

from app.schemas import ClassificationResult
from app.taxonomy import (
    CATEGORIES,
    CATEGORY_TIE_BREAK_ORDER,
    CONJUNCTIVE_LANGUAGES,
    DEFAULT_CATEGORY,
    HIGH_URGENCY_WORDS,
    LANGUAGE_MARKERS,
    LOW_URGENCY_WORDS,
    SAFETY_CRITICAL_KEYWORDS,
    SAFETY_HIGH_KEYWORDS,
)

# A phrase (two or more words) is stronger evidence than a single word.
PHRASE_WEIGHT = 2
WORD_WEIGHT = 1


# --------------------------------------------------------------------------
# Text matching helpers
# --------------------------------------------------------------------------
def normalise(text: str) -> str:
    """Lower-case, remove apostrophes and squash whitespace.

    "Didn't  COME home" -> "didnt come home"
    """
    text = text.lower()
    text = re.sub(r"[‘’'`]", "", text)  # straight and curly apostrophes
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=None)
def _pattern(keyword: str, language: str) -> re.Pattern:
    """Build (and cache) the regular expression for one keyword.

    See the module docstring of app/taxonomy.py for the three matching rules.
    """
    kw = re.escape(normalise(keyword))
    if language in CONJUNCTIVE_LANGUAGES:
        return re.compile(kw)                    # stem anywhere in a word
    if len(keyword) >= 5:
        return re.compile(r"\b" + kw)            # start of a word
    return re.compile(r"\b" + kw + r"s?\b")      # whole short word


def find_keywords(text: str, keywords_by_language: dict[str, list[str]]) -> list[str]:
    """Return the keywords (from any language) that appear in `text`.

    `text` must already be normalised. Duplicates are removed.
    """
    found: list[str] = []
    for language, keywords in keywords_by_language.items():
        for kw in keywords:
            if kw not in found and _pattern(kw, language).search(text):
                found.append(kw)
    return found


def _weight(keyword: str) -> int:
    return PHRASE_WEIGHT if " " in keyword else WORD_WEIGHT


# --------------------------------------------------------------------------
# 1. Category
# --------------------------------------------------------------------------
def score_categories(text: str) -> dict[str, tuple[int, list[str]]]:
    """Return {category: (score, matched keywords)} for every category."""
    norm = normalise(text)
    scores = {}
    for code, category in CATEGORIES.items():
        matched = find_keywords(norm, category.keywords)
        scores[code] = (sum(_weight(k) for k in matched), matched)
    return scores


def pick_category(scores: dict[str, tuple[int, list[str]]]) -> tuple[str, float]:
    """Choose the best category and a confidence between 0 and 1.

    confidence = (share of all keyword evidence that went to the winner)
                 x (how much evidence there is: 1 point = 0.5, 2 = 0.75, 3+ = 1.0)
    """
    total = sum(score for score, _ in scores.values())
    if total == 0:
        return DEFAULT_CATEGORY, 0.2  # nothing matched: a weak guess

    # Highest score wins; ties go to the category listed first in the tie-break order.
    best = max(
        CATEGORY_TIE_BREAK_ORDER,
        key=lambda c: (scores[c][0], -CATEGORY_TIE_BREAK_ORDER.index(c)),
    )
    best_score = scores[best][0]
    share = best_score / total
    strength = {1: 0.5, 2: 0.75}.get(best_score, 1.0)
    confidence = round(max(0.05, min(0.95, share * strength)), 2)
    return best, confidence


# --------------------------------------------------------------------------
# 2. Language
# --------------------------------------------------------------------------
def detect_language(text: str) -> str:
    """Guess the main language from common everyday words.

    Code-switching ("Sawubona, my child...") is normal in SA messages. A
    non-English language wins if it has at least 2 marker words and at least
    half as many as English, because parents often switch to English for
    school words ("report", "grade") even when writing in another language.
    """
    norm = normalise(text)
    counts: dict[str, int] = {}
    for language, markers in LANGUAGE_MARKERS.items():
        pattern_count = 0
        for marker in markers:
            pattern_count += len(_marker_pattern(marker, language).findall(norm))
        counts[language] = pattern_count

    english = counts.pop("en")
    best_other = max(counts, key=lambda lang: counts[lang])
    other = counts[best_other]

    if other >= 2 and other >= english * 0.5:
        return best_other
    if english > 0:
        return "en"
    if other > 0:
        return best_other
    return "unknown"


@lru_cache(maxsize=None)
def _marker_pattern(marker: str, language: str) -> re.Pattern:
    """Markers are whole words, except isiZulu/isiXhosa stems (anywhere in a word)."""
    m = re.escape(marker)
    if language in CONJUNCTIVE_LANGUAGES:
        return re.compile(m)
    return re.compile(r"\b" + m + r"\b")


# --------------------------------------------------------------------------
# 3. Urgency (before safety guardrails)
# --------------------------------------------------------------------------
def rule_urgency(text: str, category: str) -> tuple[str, list[str]]:
    """Return (urgency, matched trigger words). Safety is handled by the guardrails."""
    norm = normalise(text)
    high = find_keywords(norm, HIGH_URGENCY_WORDS)
    if high:
        return "high", high
    low = find_keywords(norm, LOW_URGENCY_WORDS)
    if low:
        return "low", low
    if category == "other":
        return "low", []
    return "medium", []


# --------------------------------------------------------------------------
# Safety terms (used by the guardrails in service.py)
# --------------------------------------------------------------------------
def find_safety_terms(text: str) -> tuple[list[str], list[str]]:
    """Return (critical terms found, high terms found) in the raw message."""
    norm = normalise(text)
    return (
        find_keywords(norm, SAFETY_CRITICAL_KEYWORDS),
        find_keywords(norm, SAFETY_HIGH_KEYWORDS),
    )


# --------------------------------------------------------------------------
# Putting it together
# --------------------------------------------------------------------------
def classify_with_rules(text: str) -> ClassificationResult:
    """Classify a message using only the rules above (no guardrails yet)."""
    scores = score_categories(text)
    category, confidence = pick_category(scores)
    urgency, urgency_words = rule_urgency(text, category)
    language = detect_language(text)

    matched = scores[category][1]
    reason = (
        f"Keywords matched: {', '.join(matched)}." if matched
        else "No category keywords matched; defaulted to 'other'."
    )
    if urgency_words:
        reason += f" Urgency words: {', '.join(urgency_words)}."

    return ClassificationResult(
        category=category,
        urgency=urgency,
        language=language,
        routed_role=CATEGORIES[category].routed_role,
        confidence=confidence,
        method="rules",
        needs_human=False,  # decided by the guardrails
        safety_flag=False,  # decided by the guardrails
        reason=reason,
    )
