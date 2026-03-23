# ---------------------------------------------------------------------------
# Structured category definitions (single source of truth)
# ---------------------------------------------------------------------------

EXPENSE_CATEGORIES: list[dict] = [
    {
        "name_key": "Alimentação",
        "icon": "🛒",
        "keywords": {
            "pt": [
                "mercado", "supermercado", "feira", "açougue", "acougue",
                "padaria", "hortifruti", "sacolão", "sacolao",
            ],
            "en": [
                "grocery", "groceries", "supermarket", "market", "butcher",
                "bakery", "produce",
            ],
            "ja": ["スーパー", "食料品", "八百屋", "パン屋", "肉屋", "市場"],
        },
    },
    {
        "name_key": "Refeição",
        "icon": "🍽️",
        "keywords": {
            "pt": [
                "jantar", "almoço", "almoco", "cafe da manha", "café da manhã",
                "cafe", "café", "cafeteria", "lanche", "restaurante", "pizza",
                "hamburguer", "hamburger", "sushi", "comida", "delivery",
                "ifood", "rappi",
            ],
            "en": [
                "dinner", "lunch", "breakfast", "coffee", "snack", "restaurant",
                "burger", "food", "meal",
            ],
            "ja": [
                "夕食", "昼食", "朝食", "コーヒー", "カフェ", "レストラン",
                "ピザ", "寿司", "食事", "ラーメン", "弁当", "居酒屋",
            ],
        },
    },
    {
        "name_key": "Transporte",
        "icon": "🚗",
        "keywords": {
            "pt": [
                "uber", "99", "taxi", "táxi", "gasolina", "combustivel",
                "combustível", "estacionamento", "pedagio", "pedágio",
                "onibus", "ônibus", "metro", "metrô", "passagem", "bilhete",
            ],
            "en": [
                "gas", "gasoline", "fuel", "parking", "toll", "bus",
                "subway", "fare", "ride", "lyft",
            ],
            "ja": [
                "タクシー", "ガソリン", "駐車場", "バス", "電車", "地下鉄",
                "切符", "交通", "定期",
            ],
        },
    },
    {
        "name_key": "Moradia",
        "icon": "🏠",
        "keywords": {
            "pt": [
                "aluguel", "condominio", "condomínio", "luz", "energia",
                "agua", "água", "gas", "gás", "internet", "telefone",
                "celular", "iptu",
            ],
            "en": [
                "rent", "condo", "electricity", "power", "water",
                "phone", "cell", "mortgage", "utility",
            ],
            "ja": [
                "家賃", "光熱費", "電気", "水道", "インターネット",
                "電話", "携帯", "住宅",
            ],
        },
    },
    {
        "name_key": "Saúde",
        "icon": "💊",
        "keywords": {
            "pt": [
                "farmacia", "farmácia", "remedio", "remédio", "medico",
                "médico", "consulta", "exame", "dentista", "hospital",
                "plano de saude", "plano de saúde",
            ],
            "en": [
                "pharmacy", "medicine", "doctor", "appointment", "exam",
                "dentist", "hospital", "health plan", "insurance", "clinic",
            ],
            "ja": [
                "薬局", "薬", "医者", "病院", "歯医者", "診察", "検査",
                "保険", "クリニック",
            ],
        },
    },
    {
        "name_key": "Educação",
        "icon": "📚",
        "keywords": {
            "pt": [
                "curso", "livro", "escola", "faculdade", "material",
                "mensalidade", "apostila",
            ],
            "en": [
                "course", "book", "school", "college", "university",
                "tuition", "textbook", "class",
            ],
            "ja": ["授業", "本", "学校", "大学", "教材", "学費", "塾"],
        },
    },
    {
        "name_key": "Lazer",
        "icon": "🎮",
        "keywords": {
            "pt": [
                "cinema", "teatro", "show", "viagem", "hotel", "bar",
                "festa", "jogo", "ingresso", "parque", "streaming",
                "netflix", "spotify", "assinatura",
            ],
            "en": [
                "movies", "theater", "concert", "trip", "travel",
                "party", "game", "ticket", "park", "subscription",
            ],
            "ja": [
                "映画", "映画館", "劇場", "コンサート", "旅行", "ホテル",
                "バー", "パーティー", "ゲーム", "チケット", "公園",
            ],
        },
    },
    {
        "name_key": "Vestuário",
        "icon": "👕",
        "keywords": {
            "pt": [
                "roupa", "calçado", "calçados", "sapato", "tenis", "tênis",
                "camisa", "calça", "vestido", "blusa", "jaqueta",
            ],
            "en": [
                "clothes", "clothing", "shoes", "sneakers", "shirt",
                "pants", "dress", "blouse", "jacket", "coat",
            ],
            "ja": [
                "服", "靴", "スニーカー", "シャツ", "ズボン", "ドレス",
                "ジャケット", "コート",
            ],
        },
    },
]

INCOME_CATEGORIES: list[dict] = [
    {
        "name_key": "Salário",
        "icon": "💼",
        "keywords": {
            "pt": ["salario", "salário", "holerite", "contracheque", "pagamento"],
            "en": ["salary", "paycheck", "wage", "wages", "payroll"],
            "ja": ["給料", "給与", "月給"],
        },
    },
    {
        "name_key": "Freelance",
        "icon": "💻",
        "keywords": {
            "pt": ["freelance", "freela", "projeto", "serviço", "servico", "consultoria"],
            "en": ["freelance", "gig", "project", "consulting", "contract"],
            "ja": ["フリーランス", "案件", "副業"],
        },
    },
    {
        "name_key": "Investimento",
        "icon": "📈",
        "keywords": {
            "pt": ["investimento", "dividendo", "rendimento", "juros", "ações", "acoes"],
            "en": ["investment", "dividend", "interest", "stocks", "returns", "yield"],
            "ja": ["投資", "配当", "利子", "株"],
        },
    },
    {
        "name_key": "Presente",
        "icon": "🎁",
        "keywords": {
            "pt": ["presente", "doação", "doacao", "herança", "heranca"],
            "en": ["gift", "donation", "inheritance"],
            "ja": ["贈り物", "プレゼント", "寄付"],
        },
    },
]

DEFAULT_CATEGORY = "Outros"
DEFAULT_INCOME_CATEGORY = "Renda Extra"

# ---------------------------------------------------------------------------
# Derived flat keyword maps (used by infer_category)
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    c["name_key"]: [kw for kwlist in c["keywords"].values() for kw in kwlist]
    for c in EXPENSE_CATEGORIES
}

INCOME_KEYWORDS: dict[str, list[str]] = {
    c["name_key"]: [kw for kwlist in c["keywords"].values() for kw in kwlist]
    for c in INCOME_CATEGORIES
}


# ---------------------------------------------------------------------------
# Keyword-based inference (unchanged behavior)
# ---------------------------------------------------------------------------

def infer_category(description: str, action_type: str = "expense") -> str:
    """Match a transaction description to a category via keyword lookup."""
    normalized = description.strip().lower()
    keywords_map = INCOME_KEYWORDS if action_type == "income" else CATEGORY_KEYWORDS
    for category, keywords in keywords_map.items():
        for keyword in keywords:
            if keyword in normalized:
                return category
    return DEFAULT_INCOME_CATEGORY if action_type == "income" else DEFAULT_CATEGORY


# ---------------------------------------------------------------------------
# Seed helpers (used by db.setup_database)
# ---------------------------------------------------------------------------

def get_all_category_seeds() -> list[dict]:
    """Return structured category data for seeding the DB.

    Each entry: {"name_key", "icon", "type", "keywords": {lang: [aliases]}}
    """
    seeds = []
    for cat in EXPENSE_CATEGORIES:
        seeds.append({**cat, "type": "expense"})
    for cat in INCOME_CATEGORIES:
        seeds.append({**cat, "type": "income"})
    seeds.append({"name_key": DEFAULT_CATEGORY, "icon": "📦", "type": "expense", "keywords": {}})
    seeds.append({"name_key": DEFAULT_INCOME_CATEGORY, "icon": "💰", "type": "income", "keywords": {}})
    return seeds
