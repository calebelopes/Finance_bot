CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Alimentação": [
        # pt
        "mercado", "supermercado", "feira", "açougue", "acougue",
        "padaria", "hortifruti", "sacolão", "sacolao",
        # en
        "grocery", "groceries", "supermarket", "market", "butcher",
        "bakery", "produce",
        # ja
        "スーパー", "食料品", "八百屋", "パン屋", "肉屋", "市場",
    ],
    "Refeição": [
        # pt
        "jantar", "almoço", "almoco", "cafe da manha", "café da manhã",
        "cafe", "café", "cafeteria", "lanche", "restaurante", "pizza",
        "hamburguer", "hamburger", "sushi", "comida", "delivery",
        "ifood", "rappi",
        # en
        "dinner", "lunch", "breakfast", "coffee", "snack", "restaurant",
        "burger", "food", "meal",
        # ja
        "夕食", "昼食", "朝食", "コーヒー", "カフェ", "レストラン",
        "ピザ", "寿司", "食事", "ラーメン", "弁当", "居酒屋",
    ],
    "Transporte": [
        # pt
        "uber", "99", "taxi", "táxi", "gasolina", "combustivel",
        "combustível", "estacionamento", "pedagio", "pedágio",
        "onibus", "ônibus", "metro", "metrô", "passagem", "bilhete",
        # en
        "gas", "gasoline", "fuel", "parking", "toll", "bus",
        "subway", "fare", "ride", "lyft",
        # ja
        "タクシー", "ガソリン", "駐車場", "バス", "電車", "地下鉄",
        "切符", "交通", "定期",
    ],
    "Moradia": [
        # pt
        "aluguel", "condominio", "condomínio", "luz", "energia",
        "agua", "água", "gas", "gás", "internet", "telefone",
        "celular", "iptu",
        # en
        "rent", "condo", "electricity", "power", "water",
        "phone", "cell", "mortgage", "utility",
        # ja
        "家賃", "光熱費", "電気", "水道", "インターネット",
        "電話", "携帯", "住宅",
    ],
    "Saúde": [
        # pt
        "farmacia", "farmácia", "remedio", "remédio", "medico",
        "médico", "consulta", "exame", "dentista", "hospital",
        "plano de saude", "plano de saúde",
        # en
        "pharmacy", "medicine", "doctor", "appointment", "exam",
        "dentist", "hospital", "health plan", "insurance", "clinic",
        # ja
        "薬局", "薬", "医者", "病院", "歯医者", "診察", "検査",
        "保険", "クリニック",
    ],
    "Educação": [
        # pt
        "curso", "livro", "escola", "faculdade", "material",
        "mensalidade", "apostila",
        # en
        "course", "book", "school", "college", "university",
        "tuition", "textbook", "class",
        # ja
        "授業", "本", "学校", "大学", "教材", "学費", "塾",
    ],
    "Lazer": [
        # pt
        "cinema", "teatro", "show", "viagem", "hotel", "bar",
        "festa", "jogo", "ingresso", "parque", "streaming",
        "netflix", "spotify", "assinatura",
        # en
        "movies", "theater", "concert", "trip", "travel",
        "party", "game", "ticket", "park", "subscription",
        # ja
        "映画", "映画館", "劇場", "コンサート", "旅行", "ホテル",
        "バー", "パーティー", "ゲーム", "チケット", "公園",
    ],
    "Vestuário": [
        # pt
        "roupa", "calçado", "calçados", "sapato", "tenis", "tênis",
        "camisa", "calça", "vestido", "blusa", "jaqueta",
        # en
        "clothes", "clothing", "shoes", "sneakers", "shirt",
        "pants", "dress", "blouse", "jacket", "coat",
        # ja
        "服", "靴", "スニーカー", "シャツ", "ズボン", "ドレス",
        "ジャケット", "コート",
    ],
}

DEFAULT_CATEGORY = "Outros"

INCOME_KEYWORDS: dict[str, list[str]] = {
    "Salário": [
        # pt
        "salario", "salário", "holerite", "contracheque", "pagamento",
        # en
        "salary", "paycheck", "wage", "wages", "payroll",
        # ja
        "給料", "給与", "月給",
    ],
    "Freelance": [
        # pt
        "freelance", "freela", "projeto", "serviço", "servico", "consultoria",
        # en
        "freelance", "gig", "project", "consulting", "contract",
        # ja
        "フリーランス", "案件", "副業",
    ],
    "Investimento": [
        # pt
        "investimento", "dividendo", "rendimento", "juros", "ações", "acoes",
        # en
        "investment", "dividend", "interest", "stocks", "returns", "yield",
        # ja
        "投資", "配当", "利子", "株",
    ],
    "Presente": [
        # pt
        "presente", "doação", "doacao", "herança", "heranca",
        # en
        "gift", "donation", "inheritance",
        # ja
        "贈り物", "プレゼント", "寄付",
    ],
}

DEFAULT_INCOME_CATEGORY = "Renda Extra"


def infer_category(action: str, action_type: str = "expense") -> str:
    """Match an action description to a category via keyword lookup."""
    normalized = action.strip().lower()
    keywords_map = INCOME_KEYWORDS if action_type == "income" else CATEGORY_KEYWORDS
    for category, keywords in keywords_map.items():
        for keyword in keywords:
            if keyword in normalized:
                return category
    return DEFAULT_INCOME_CATEGORY if action_type == "income" else DEFAULT_CATEGORY
