from utils.export import generate_csv, generate_pdf

_SAMPLE_TXS = [
    {
        "id": 1,
        "description": "jantar",
        "amount_original": 25.50,
        "category": "Refeição",
        "type": "expense",
        "currency_code": "BRL",
        "created_at": "2025-03-15T18:30:00",
    },
    {
        "id": 2,
        "description": "salary",
        "amount_original": 5000.0,
        "category": "Salário",
        "type": "income",
        "currency_code": "BRL",
        "created_at": "2025-03-01T09:00:00",
    },
]


class TestGenerateCSV:
    def test_returns_bytes(self):
        result = generate_csv(_SAMPLE_TXS, "pt")
        assert isinstance(result, bytes)

    def test_contains_headers(self):
        result = generate_csv(_SAMPLE_TXS, "pt").decode("utf-8-sig")
        assert "Descrição" in result
        assert "Valor" in result

    def test_contains_data(self):
        result = generate_csv(_SAMPLE_TXS, "en").decode("utf-8-sig")
        assert "jantar" in result
        assert "salary" in result

    def test_english_headers(self):
        result = generate_csv(_SAMPLE_TXS, "en").decode("utf-8-sig")
        assert "Description" in result
        assert "Amount" in result

    def test_japanese_headers(self):
        result = generate_csv(_SAMPLE_TXS, "ja").decode("utf-8-sig")
        assert "説明" in result

    def test_empty_transactions(self):
        result = generate_csv([], "pt")
        assert isinstance(result, bytes)
        lines = result.decode("utf-8-sig").strip().split("\n")
        assert len(lines) == 1


class TestGeneratePDF:
    def test_returns_bytes(self):
        result = generate_pdf(_SAMPLE_TXS, "pt")
        assert isinstance(result, bytes)

    def test_pdf_header(self):
        result = generate_pdf(_SAMPLE_TXS, "en", "month")
        assert result[:4] == b"%PDF"

    def test_empty_transactions(self):
        result = generate_pdf([], "pt")
        assert isinstance(result, bytes)
        assert result[:4] == b"%PDF"
