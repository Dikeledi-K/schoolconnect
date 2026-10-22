"""The taxonomy is the single source of truth, so check it is internally consistent."""

from app.taxonomy import (
    CATEGORIES,
    CATEGORY_TIE_BREAK_ORDER,
    DEFAULT_CATEGORY,
    LANGUAGES,
    SAFETY_CRITICAL_KEYWORDS,
    SAFETY_HIGH_KEYWORDS,
    STAFF_ROLES,
    STATUSES,
    URGENCY_LEVELS,
    WELFARE_CATEGORY,
    max_urgency,
    taxonomy_as_dict,
)

EXPECTED_CATEGORIES = {
    "admissions", "fees_exemptions", "academic", "learner_welfare",
    "transport", "it_portal", "other",
}


def test_required_categories_exist():
    assert set(CATEGORIES) == EXPECTED_CATEGORIES
    assert DEFAULT_CATEGORY in CATEGORIES
    assert WELFARE_CATEGORY in CATEGORIES


def test_every_category_is_complete():
    for code, cat in CATEGORIES.items():
        assert cat.code == code
        assert cat.display_name and cat.description
        assert cat.routed_role in STAFF_ROLES
        assert cat.keywords.get("en"), f"{code} has no English keywords"
        assert set(cat.keywords) <= set(LANGUAGES), f"{code} uses an unknown language code"


def test_non_english_keywords_present():
    for lang in ("zu", "st", "af"):
        assert any(cat.keywords.get(lang) for cat in CATEGORIES.values())


def test_keywords_are_lower_case():
    groups = [c.keywords for c in CATEGORIES.values()] + [SAFETY_CRITICAL_KEYWORDS, SAFETY_HIGH_KEYWORDS]
    for group in groups:
        for words in group.values():
            for w in words:
                assert w == w.lower(), w


def test_welfare_routes_to_deputy_principal():
    assert CATEGORIES[WELFARE_CATEGORY].routed_role == "deputy_principal"


def test_tie_break_lists_every_category_once_with_welfare_first():
    assert sorted(CATEGORY_TIE_BREAK_ORDER) == sorted(CATEGORIES)
    assert CATEGORY_TIE_BREAK_ORDER[0] == WELFARE_CATEGORY


def test_levels_languages_statuses():
    assert URGENCY_LEVELS == ["low", "medium", "high", "critical"]
    assert set(LANGUAGES) == {"en", "zu", "st", "af", "xh", "unknown"}
    assert STATUSES == ["new", "in_progress", "resolved"]


def test_max_urgency_only_raises():
    assert max_urgency("low", "high") == "high"
    assert max_urgency("critical", "high") == "critical"
    assert max_urgency("medium", "medium") == "medium"


def test_taxonomy_as_dict_has_no_keywords():
    data = taxonomy_as_dict()
    assert len(data["categories"]) == len(CATEGORIES)
    assert "keywords" not in data["categories"][0]
