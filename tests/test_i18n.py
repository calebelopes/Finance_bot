from utils.i18n import cat_name, d, detect_lang, fmt_currency, t


class TestDetectLang:
    def test_pt_br(self):
        assert detect_lang("pt-br") == "pt"

    def test_en(self):
        assert detect_lang("en") == "en"

    def test_ja(self):
        assert detect_lang("ja") == "ja"

    def test_en_us(self):
        assert detect_lang("en-US") == "en"

    def test_unknown_defaults_pt(self):
        assert detect_lang("fr") == "pt"

    def test_none_defaults_pt(self):
        assert detect_lang(None) == "pt"


class TestFmtCurrency:
    def test_pt(self):
        assert fmt_currency(1234.56, "pt") == "R$ 1.234,56"

    def test_en(self):
        assert fmt_currency(1234.56, "en") == "$1,234.56"

    def test_ja(self):
        assert fmt_currency(1234, "ja") == "¥1,234"


class TestBotTranslation:
    def test_basic_lookup(self):
        assert "Bem-vindo" in t("start", "pt")
        assert "Welcome" in t("start", "en")
        assert "ようこそ" in t("start", "ja")

    def test_placeholder_expense(self):
        result = t("stored_expense", "en", id=1, action="dinner", value="$20.00", category="Food")
        assert "#1" in result
        assert "dinner" in result

    def test_placeholder_income(self):
        result = t("stored_income", "en", id=1, action="salary", value="$5,000.00", category="Salary")
        assert "#1" in result
        assert "salary" in result

    def test_fallback_to_pt(self):
        result = t("start", "zz")
        assert "Bem-vindo" in result


class TestCatName:
    def test_pt(self):
        assert cat_name("Alimentação", "pt") == "Alimentação"
        assert cat_name("Outros", "pt") == "Outros"

    def test_en(self):
        assert cat_name("Alimentação", "en") == "Groceries"
        assert cat_name("Refeição", "en") == "Meals"
        assert cat_name("Outros", "en") == "Other"

    def test_ja(self):
        assert cat_name("Alimentação", "ja") == "食料品"
        assert cat_name("Lazer", "ja") == "娯楽"
        assert cat_name("Outros", "ja") == "その他"

    def test_income_categories_en(self):
        assert cat_name("Salário", "en") == "Salary"
        assert cat_name("Freelance", "en") == "Freelance"
        assert cat_name("Investimento", "en") == "Investment"
        assert cat_name("Renda Extra", "en") == "Extra Income"

    def test_income_categories_ja(self):
        assert cat_name("Salário", "ja") == "給料"
        assert cat_name("Investimento", "ja") == "投資"
        assert cat_name("Renda Extra", "ja") == "臨時収入"

    def test_unknown_key_returns_as_is(self):
        assert cat_name("UnknownCat", "en") == "UnknownCat"


class TestDashTranslation:
    def test_basic_lookup(self):
        assert "Entrar" in d("login_submit", "pt")
        assert "Log in" in d("login_submit", "en")
        assert "ログイン" in d("login_submit", "ja")

    def test_placeholder(self):
        result = d("showing", "en", shown=5, total=10)
        assert "5" in result
        assert "10" in result
