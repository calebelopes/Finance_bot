import pytest

from utils.parser import detect_currency, format_currency, parse_action_value, parse_number_ptbr


class TestParseNumberPtBr:
    def test_integer(self):
        assert parse_number_ptbr("20") == 20.0

    def test_decimal_dot(self):
        assert parse_number_ptbr("20.5") == 20.5

    def test_decimal_comma_ptbr(self):
        assert parse_number_ptbr("20,50") == 20.5

    def test_thousands_dot_decimal_comma(self):
        assert parse_number_ptbr("1.234,56") == 1234.56

    def test_thousands_comma_decimal_dot(self):
        assert parse_number_ptbr("1,234.56") == 1234.56

    def test_large_number(self):
        assert parse_number_ptbr("10.000,00") == 10000.0

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_number_ptbr("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            parse_number_ptbr("   ")

    def test_not_a_number_raises(self):
        with pytest.raises(ValueError):
            parse_number_ptbr("abc")

    def test_spaces_stripped(self):
        assert parse_number_ptbr("  12,50  ") == 12.5


class TestDetectCurrency:
    def test_usd_variants(self):
        assert detect_currency("usd") == "USD"
        assert detect_currency("dollar") == "USD"
        assert detect_currency("dollars") == "USD"
        assert detect_currency("dólares") == "USD"

    def test_brl(self):
        assert detect_currency("brl") == "BRL"
        assert detect_currency("reais") == "BRL"

    def test_eur(self):
        assert detect_currency("eur") == "EUR"
        assert detect_currency("euro") == "EUR"

    def test_jpy(self):
        assert detect_currency("jpy") == "JPY"
        assert detect_currency("yen") == "JPY"
        assert detect_currency("ienes") == "JPY"

    def test_gbp(self):
        assert detect_currency("gbp") == "GBP"
        assert detect_currency("pound") == "GBP"
        assert detect_currency("libras") == "GBP"

    def test_unknown(self):
        assert detect_currency("xyz") is None
        assert detect_currency("banana") is None

    def test_case_insensitive(self):
        assert detect_currency("USD") == "USD"
        assert detect_currency("Eur") == "EUR"


class TestParseActionValue:
    def test_simple(self):
        action, value, cur = parse_action_value("jantar 20,50")
        assert action == "jantar"
        assert value == 20.5
        assert cur is None

    def test_multi_word_action(self):
        action, value, cur = parse_action_value("cafe da manha 12")
        assert action == "cafe da manha"
        assert value == 12.0
        assert cur is None

    def test_single_word_raises(self):
        with pytest.raises(ValueError):
            parse_action_value("hello")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_action_value("")

    def test_value_with_thousands(self):
        action, value, cur = parse_action_value("mercado 1.234,56")
        assert action == "mercado"
        assert value == 1234.56

    def test_extra_whitespace_normalized(self):
        action, value, cur = parse_action_value("  jantar   20,50  ")
        assert action == "jantar"
        assert value == 20.5

    def test_currency_usd(self):
        action, value, cur = parse_action_value("dinner 30 usd")
        assert action == "dinner"
        assert value == 30.0
        assert cur == "USD"

    def test_currency_dollars(self):
        action, value, cur = parse_action_value("dinner 25.50 dollars")
        assert action == "dinner"
        assert value == 25.5
        assert cur == "USD"

    def test_currency_yen(self):
        action, value, cur = parse_action_value("夕食 3000 yen")
        assert action == "夕食"
        assert value == 3000.0
        assert cur == "JPY"

    def test_currency_eur(self):
        action, value, cur = parse_action_value("hotel 120 euro")
        assert action == "hotel"
        assert value == 120.0
        assert cur == "EUR"

    def test_currency_reais(self):
        action, value, cur = parse_action_value("jantar 50 reais")
        assert action == "jantar"
        assert value == 50.0
        assert cur == "BRL"

    def test_currency_libras(self):
        action, value, cur = parse_action_value("taxi 15 libras")
        assert action == "taxi"
        assert value == 15.0
        assert cur == "GBP"


class TestFormatCurrency:
    def test_simple(self):
        assert format_currency(20.5) == "20,50"

    def test_thousands(self):
        assert format_currency(1234.56) == "1.234,56"

    def test_zero(self):
        assert format_currency(0) == "0,00"

    def test_large(self):
        assert format_currency(10000.0) == "10.000,00"

    def test_cents_only(self):
        assert format_currency(0.99) == "0,99"
