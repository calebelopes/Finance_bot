# Finance Telegram Bot

Bot do Telegram para registrar e controlar gastos pessoais.
Envie mensagens pelo Telegram e tenha seus gastos organizados com categorização automática, consultas por período e resumo por categoria.

---

## Funcionalidades

- **Registro rápido** de gastos via mensagem de texto
- **Categorização automática** (Alimentação, Refeição, Transporte, etc.)
- **Consulta de gastos** por período (`/today`, `/week`, `/month`)
- **Resumo por categoria** (`/summary`)
- **Edição e exclusão** de registros
- **Formato pt-BR** (vírgula decimal: `20,50` / milhares: `1.234,56`)
- **Controle de acesso** por ID do Telegram

---

## Comandos

| Comando | Descrição |
|---------|-----------|
| `/start` | Mensagem de boas-vindas |
| `/help` | Lista de comandos |
| `/today` | Gastos de hoje |
| `/week` | Gastos da semana |
| `/month` | Gastos do mês |
| `/summary` | Resumo por categoria (mês atual) |
| `/delete <id>` | Apagar um gasto |
| `/edit <id> <valor>` | Editar valor de um gasto |

Para registrar um gasto, envie uma mensagem com a descrição e o valor:

```
jantar 20,50
mercado 135,90
cafe da manha 12
uber 25
```

---

## Setup

### 1. Clone e instale dependências

```bash
git clone <repo-url>
cd Finance_bot
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .\.venv\Scripts\Activate.ps1   # Windows PowerShell
pip install -r requirements.txt
```

### 2. Configure variáveis de ambiente

Copie o exemplo e edite:

```bash
cp .env.example .env
# Edite .env com seu token do BotFather
```

Ou defina diretamente no terminal:

```bash
export TOKEN="seu_token_do_botfather"
```

### 3. Execute

```bash
python -m bot.main
```

---

## Variáveis de Ambiente

| Variável | Obrigatório | Descrição |
|----------|:-----------:|-----------|
| `TOKEN` | Sim | Token do bot (@BotFather) |
| `ALLOWED_USERS` | Não | IDs de usuários permitidos (separados por vírgula) |
| `TIMEZONE` | Não | Fuso horário (padrão: `America/Sao_Paulo`) |
| `USE_SYSTEM_CA` | Não | `1` para usar certificados do sistema (redes corporativas) |
| `TELEGRAM_CA_BUNDLE` | Não | Caminho para arquivo PEM de CA customizado |

---

## Categorias Automáticas

O bot categoriza gastos automaticamente com base na descrição:

| Categoria | Exemplos de palavras-chave |
|-----------|---------------------------|
| Alimentação | mercado, supermercado, feira, padaria |
| Refeição | jantar, almoço, café, restaurante, pizza |
| Transporte | uber, gasolina, estacionamento, ônibus |
| Moradia | aluguel, condomínio, luz, água, internet |
| Saúde | farmácia, remédio, médico, consulta |
| Educação | curso, livro, escola, faculdade |
| Lazer | cinema, viagem, hotel, bar, netflix |
| Vestuário | roupa, sapato, camisa, calça |
| Outros | (padrão quando não há correspondência) |

---

## Banco de Dados (SQLite)

Arquivo: `data/data.db` (criado automaticamente)

### Tabelas

- **`users`** — id (Telegram), username
- **`actions`** — user_id, action, value, category, created_at (UTC)
- **`usage_events`** — user_id, event_type, created_at
- **`app_events`** — event_type, created_at

Migrações são aplicadas automaticamente em `setup_database()`.

---

## Docker

```bash
docker build -t finance-bot .
docker run -e TOKEN="seu_token" finance-bot
```

Com persistência de dados:

```bash
docker run -e TOKEN="seu_token" -v ./data:/app/data finance-bot
```

---

## Desenvolvimento

### Instalar dependências de desenvolvimento

```bash
pip install -r requirements-dev.txt
```

### Executar testes

```bash
pytest tests/ -v
```

### Linting

```bash
ruff check .
```

---

## Estrutura do Projeto

```
Finance_bot/
├── bot/
│   ├── __init__.py
│   └── main.py              # Handlers e polling
├── utils/
│   ├── __init__.py
│   ├── categories.py         # Categorização automática
│   ├── db.py                 # SQLite (setup, CRUD, queries)
│   ├── messages.py           # Textos do bot (pt-BR)
│   └── parser.py             # Parsing de números e ações
├── tests/
│   ├── test_categories.py
│   ├── test_db.py
│   └── test_parser.py
├── data/
│   └── .gitkeep
├── .env.example
├── .github/workflows/ci.yml
├── .gitignore
├── Dockerfile
├── pyproject.toml
├── README.md
├── requirements.txt
└── requirements-dev.txt
```

---

## Deploy / 24×7

O bot roda em **polling**, então precisa de um processo sempre ativo.

- **VM** (Oracle Free Tier, AWS EC2, etc.) — mais controle, fácil manter 24/7
- **PaaS** (Render, Fly.io, Railway) — deploy mais simples, free tier pode ter limitações
- **Docker** — ideal para qualquer ambiente com containerização
