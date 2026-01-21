# Finance Telegram Bot (pt-BR)

Um bot do Telegram para **registrar ações/gastos** em um **SQLite**.

Você envia mensagens no formato:

- `<ação/descrição> <valor>`
- Exemplos:
  - `jantar 20,50`
  - `mercado 1.234,56`
  - `cafe da manha 12`

O bot salva as ações no banco e mantém:

- **usuários** (id do Telegram + username)
- **ações por usuário** (inclui data/hora)
- **log de uso** (somente quando uma ação foi salva)
- **log do app** (1x quando o app inicia)

---

## Como rodar (Windows / PowerShell)

### 1) Criar/ativar venv (opcional, recomendado)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2) Instalar dependências

```powershell
pip install -r requirements.txt
```

### 3) Definir variáveis de ambiente

Defina o token do bot:

```powershell
$env:TOKEN="SEU_TOKEN_DO_BOTFATHER"
```

Se você estiver em rede corporativa com proxy/inspeção SSL e receber erro de certificado,
use UMA das opções abaixo:

- **Opção A (recomendada no Windows)**: usar o repositório de certificados do Windows

```powershell
$env:USE_SYSTEM_CA="1"
```

- **Opção B**: apontar para um CA bundle `.pem` da sua empresa

```powershell
$env:TELEGRAM_CA_BUNDLE="C:\caminho\ca-corporativo.pem"
```

### 4) Rodar

Na raiz do projeto:

```powershell
python -m bot.main
```

Também funciona rodando direto do diretório `bot\`:

```powershell
cd .\bot\
python .\main.py
```

---

## Funcionalidades

- **`/start`**: mostra instruções (pt-BR)
- **Greeting**: responde quando o usuário envia `oi`, `olá`, `bom dia`, etc.
- **Registro de ação**:
  - Envia `<descrição> <valor>`
  - Aceita vírgula decimal (pt-BR): `12,50`
  - Aceita milhares: `1.234,56`

---

## Banco de dados (SQLite)

Arquivo: `data/data.db`

Tabelas principais:

- **`users`**
  - `id` (INTEGER PRIMARY KEY): id do usuário no Telegram
  - `username` (TEXT): username do Telegram (pode ser `NULL`)

- **`actions`**
  - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
  - `user_id` (INTEGER): FK para `users.id`
  - `action` (TEXT): descrição
  - `value` (REAL): valor numérico
  - `created_at` (TEXT): timestamp ISO-8601 (UTC)

- **`usage_events`** (sem conteúdo da mensagem)
  - `user_id`
  - `event_type` (ex.: `action_stored`)
  - `created_at`

- **`app_events`**
  - `event_type` (ex.: `app_started`)
  - `created_at`

O `setup_database()` faz migrações leves (ex.: adicionar colunas faltantes).

---

## Deploy / 24x7 (visão geral)

O bot roda em **polling**, então precisa de um processo sempre ativo.

- **VM (ex.: Oracle Free Tier, AWS EC2, etc.)**: mais controle e mais fácil manter 24/7.
- **PaaS (Render/Fly/Railway)**: deploy mais simples, mas free tier pode ter limitações.

---

## Estrutura do projeto

- `bot/main.py`: entrypoint do bot (handlers e polling)
- `utils/db.py`: SQLite (setup + inserts)
- `utils/messages.py`: textos do bot (pt-BR)
- `data/data.db`: banco SQLite

