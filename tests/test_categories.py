from utils.categories import DEFAULT_CATEGORY, DEFAULT_INCOME_CATEGORY, infer_category


class TestInferCategory:
    def test_alimentacao(self):
        assert infer_category("mercado") == "Alimentação"
        assert infer_category("supermercado") == "Alimentação"
        assert infer_category("padaria") == "Alimentação"

    def test_refeicao(self):
        assert infer_category("jantar") == "Refeição"
        assert infer_category("cafe da manha") == "Refeição"
        assert infer_category("almoço") == "Refeição"
        assert infer_category("restaurante") == "Refeição"

    def test_transporte(self):
        assert infer_category("uber") == "Transporte"
        assert infer_category("gasolina") == "Transporte"
        assert infer_category("estacionamento") == "Transporte"

    def test_moradia(self):
        assert infer_category("aluguel") == "Moradia"
        assert infer_category("internet") == "Moradia"
        assert infer_category("luz") == "Moradia"

    def test_saude(self):
        assert infer_category("farmacia") == "Saúde"
        assert infer_category("consulta médica") == "Saúde"
        assert infer_category("dentista") == "Saúde"

    def test_educacao(self):
        assert infer_category("curso") == "Educação"
        assert infer_category("livro") == "Educação"

    def test_lazer(self):
        assert infer_category("cinema") == "Lazer"
        assert infer_category("netflix") == "Lazer"
        assert infer_category("viagem") == "Lazer"

    def test_vestuario(self):
        assert infer_category("roupa") == "Vestuário"
        assert infer_category("sapato") == "Vestuário"

    def test_default_category(self):
        assert infer_category("something random") == DEFAULT_CATEGORY
        assert infer_category("xyz") == DEFAULT_CATEGORY

    def test_case_insensitive(self):
        assert infer_category("MERCADO") == "Alimentação"
        assert infer_category("Jantar") == "Refeição"

    def test_partial_match_in_longer_string(self):
        assert infer_category("supermercado extra") == "Alimentação"
        assert infer_category("uber black") == "Transporte"

    def test_english_keywords(self):
        assert infer_category("grocery store") == "Alimentação"
        assert infer_category("dinner") == "Refeição"
        assert infer_category("parking") == "Transporte"
        assert infer_category("rent") == "Moradia"
        assert infer_category("pharmacy") == "Saúde"
        assert infer_category("course") == "Educação"
        assert infer_category("movies") == "Lazer"
        assert infer_category("shoes") == "Vestuário"

    def test_japanese_keywords(self):
        assert infer_category("スーパー") == "Alimentação"
        assert infer_category("夕食") == "Refeição"
        assert infer_category("タクシー") == "Transporte"
        assert infer_category("家賃") == "Moradia"
        assert infer_category("薬局") == "Saúde"
        assert infer_category("学校") == "Educação"
        assert infer_category("映画") == "Lazer"
        assert infer_category("靴") == "Vestuário"


class TestIncomeCategories:
    def test_salary_pt(self):
        assert infer_category("salario", "income") == "Salário"

    def test_salary_en(self):
        assert infer_category("salary", "income") == "Salário"

    def test_salary_ja(self):
        assert infer_category("給料", "income") == "Salário"

    def test_freelance(self):
        assert infer_category("freelance", "income") == "Freelance"

    def test_investment(self):
        assert infer_category("dividend", "income") == "Investimento"
        assert infer_category("investimento", "income") == "Investimento"
        assert infer_category("配当", "income") == "Investimento"

    def test_gift(self):
        assert infer_category("gift", "income") == "Presente"
        assert infer_category("presente", "income") == "Presente"

    def test_default_income_category(self):
        assert infer_category("random thing", "income") == DEFAULT_INCOME_CATEGORY

    def test_expense_does_not_use_income_keywords(self):
        assert infer_category("salary", "expense") == DEFAULT_CATEGORY
