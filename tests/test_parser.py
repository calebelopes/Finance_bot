import pytest

from utils.parser import format_currency, parse_action_value, parse_number_ptbr


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


class TestParseActionValue:
    def test_simple(self):
        action, value = parse_action_value("jantar 20,50")
        assert action == "jantar"
        assert value == 20.5

    def test_multi_word_action(self):
        action, value = parse_action_value("cafe da manha 12")
        assert action == "cafe da manha"
        assert value == 12.0

    def test_single_word_raises(self):
        with pytest.raises(ValueError):
            parse_action_value("hello")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_action_value("")

    def test_value_with_thousands(self):
        action, value = parse_action_value("mercado 1.234,56")
        assert action == "mercado"
        assert value == 1234.56

    def test_extra_whitespace_normalized(self):
        action, value = parse_action_value("  jantar   20,50  ")
        assert action == "jantar"
        assert value == 20.5


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
