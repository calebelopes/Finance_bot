"""Tests for Module 7 - NLP enhancements (parser, fuzzy matching, confidence)."""

import pytest

from utils.categories import DEFAULT_CATEGORY, get_top_categories, infer_category_with_confidence
from utils.parser import ParseResult, clean_description, detect_date_offset, parse_smart

# ---------------------------------------------------------------------------
# Date expression detection
# ---------------------------------------------------------------------------


class TestDetectDateOffset:
    def test_portuguese_ontem(self):
        offset, cleaned = detect_date_offset("ontem jantar 30")
        assert offset == -1
        assert "ontem" not in cleaned
        assert "jantar" in cleaned
        assert "30" in cleaned

    def test_portuguese_hoje(self):
        offset, cleaned = detect_date_offset("hoje lanche 15")
        assert offset == 0

    def test_portuguese_anteontem(self):
        offset, cleaned = detect_date_offset("anteontem mercado 50")
        assert offset == -2

    def test_english_yesterday(self):
        offset, cleaned = detect_date_offset("yesterday dinner 30")
        assert offset == -1
        assert "yesterday" not in cleaned

    def test_english_today(self):
        offset, cleaned = detect_date_offset("today lunch 20")
        assert offset == 0

    def test_english_day_before_yesterday(self):
        offset, cleaned = detect_date_offset("day before yesterday coffee 5")
        assert offset == -2
        assert "day before yesterday" not in cleaned.lower()

    def test_japanese_kinou(self):
        offset, cleaned = detect_date_offset("昨日 夕食 3000")
        assert offset == -1

    def test_japanese_kyou(self):
        offset, cleaned = detect_date_offset("今日 ランチ 1200")
        assert offset == 0

    def test_japanese_hiragana_kinou(self):
        offset, cleaned = detect_date_offset("きのう ラーメン 900")
        assert offset == -1

    def test_no_date(self):
        offset, cleaned = detect_date_offset("jantar 30")
        assert offset is None
        assert cleaned == "jantar 30"

    def test_antes_de_ontem_phrase(self):
        offset, cleaned = detect_date_offset("antes de ontem uber 25")
        assert offset == -2
        assert "antes de ontem" not in cleaned.lower()


# ---------------------------------------------------------------------------
# Noise word cleanup
# ---------------------------------------------------------------------------


class TestCleanDescription:
    def test_pt_prepositions(self):
        assert clean_description("jantar no shopping") == "jantar shopping"

    def test_en_articles(self):
        assert clean_description("lunch at the mall") == "lunch mall"

    def test_preserves_meaningful_words(self):
        assert clean_description("mercado") == "mercado"

    def test_empty_after_cleanup_returns_original(self):
        result = clean_description("no na da")
        assert result == "no na da"

    def test_japanese_particles(self):
        assert clean_description("レストラン で 食事") == "レストラン 食事"


# ---------------------------------------------------------------------------
# parse_smart — enhanced parser
# ---------------------------------------------------------------------------


class TestParseSmart:
    def test_standard_format(self):
        r = parse_smart("jantar 30")
        assert r.value == 30.0
        assert r.description == "jantar"
        assert r.date_offset is None

    def test_standard_with_currency(self):
        r = parse_smart("dinner 30 usd")
        assert r.value == 30.0
        assert r.description == "dinner"
        assert r.currency == "USD"

    def test_date_ontem(self):
        r = parse_smart("ontem jantar 30")
        assert r.value == 30.0
        assert r.date_offset == -1
        assert "jantar" in r.description

    def test_date_yesterday_with_currency(self):
        r = parse_smart("yesterday dinner 25 usd")
        assert r.value == 25.0
        assert r.currency == "USD"
        assert r.date_offset == -1

    def test_flexible_position_value_first(self):
        r = parse_smart("30 jantar")
        assert r.value == 30.0
        assert "jantar" in r.description

    def test_flexible_position_value_middle(self):
        r = parse_smart("paid 30 dinner")
        assert r.value == 30.0
        assert "dinner" in r.description

    def test_natural_phrase_pt(self):
        r = parse_smart("almocei no shopping 45 reais")
        assert r.value == 45.0
        assert r.currency == "BRL"
        assert "shopping" in r.description

    def test_natural_phrase_en(self):
        r = parse_smart("spent 50 on groceries")
        assert r.value == 50.0
        assert "groceries" in r.description

    def test_backdate_plus_flex_position(self):
        r = parse_smart("ontem 45 mercado")
        assert r.value == 45.0
        assert r.date_offset == -1
        assert "mercado" in r.description

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_smart("hello world nothing")


# ---------------------------------------------------------------------------
# Fuzzy matching + confidence
# ---------------------------------------------------------------------------


class TestInferCategoryWithConfidence:
    def test_exact_match_confidence_1(self):
        cat, conf = infer_category_with_confidence("jantar")
        assert cat == "Refeição"
        assert conf == 1.0

    def test_typo_resturante(self):
        cat, conf = infer_category_with_confidence("resturante")
        assert cat == "Refeição"
        assert 0.78 <= conf < 1.0

    def test_typo_farmcia(self):
        cat, conf = infer_category_with_confidence("farmcia")
        assert cat == "Saúde"
        assert 0.78 <= conf < 1.0

    def test_typo_supermecado(self):
        cat, conf = infer_category_with_confidence("supermecado")
        assert cat == "Alimentação"
        assert 0.78 <= conf < 1.0

    def test_unknown_description(self):
        cat, conf = infer_category_with_confidence("xyzabc")
        assert cat == DEFAULT_CATEGORY
        assert conf == 0.0

    def test_income_exact(self):
        cat, conf = infer_category_with_confidence("salary", "income")
        assert cat == "Salário"
        assert conf == 1.0

    def test_income_fuzzy(self):
        cat, conf = infer_category_with_confidence("salry", "income")
        assert cat == "Salário"
        assert 0.78 <= conf < 1.0


class TestGetTopCategories:
    def test_returns_list(self):
        result = get_top_categories("restaurante")
        assert isinstance(result, list)
        assert len(result) >= 1
        assert result[0][0] == "Refeição"

    def test_fuzzy_returns_candidates(self):
        result = get_top_categories("resturante")
        names = [cat for cat, _ in result]
        assert "Refeição" in names

    def test_max_n(self):
        result = get_top_categories("comida", n=2)
        assert len(result) <= 2

    def test_unknown_returns_low_scores(self):
        result = get_top_categories("xyznothing")
        for _, score in result:
            assert score < 0.78


# ---------------------------------------------------------------------------
# ParseResult dataclass
# ---------------------------------------------------------------------------


class TestParseResult:
    def test_defaults(self):
        r = ParseResult(description="test", value=10.0)
        assert r.currency is None
        assert r.date_offset is None
        assert r.raw_description == ""
