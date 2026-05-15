"""
Internationalization module for Finance Bot.

Supports: pt (Portuguese-BR), en (English-US), ja (Japanese).
"""

SUPPORTED_LANGS = {"pt", "en", "ja"}
DEFAULT_LANG = "pt"

# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------


def detect_lang(telegram_language_code: str | None) -> str:
    """Map a Telegram language_code (e.g. 'pt-br', 'en', 'ja') to a supported lang key."""
    if not telegram_language_code:
        return DEFAULT_LANG
    code = telegram_language_code.lower().split("-")[0]
    if code in SUPPORTED_LANGS:
        return code
    return DEFAULT_LANG


# ---------------------------------------------------------------------------
# Currency formatting
# ---------------------------------------------------------------------------


_CURRENCY_SYMBOLS = {"BRL": "R$", "USD": "$", "EUR": "€", "JPY": "¥", "GBP": "£"}


def fmt_currency(value: float, lang: str = "pt", currency_code: str | None = None) -> str:
    """Format a float as a locale-appropriate currency string.

    If *currency_code* is given, it takes precedence over the lang-based default.
    """
    symbol = _CURRENCY_SYMBOLS.get(currency_code, "") if currency_code else ""
    no_decimals = currency_code == "JPY" if currency_code else (lang == "ja")

    if no_decimals:
        formatted = f"{value:,.0f}"
    elif lang == "pt":
        s = f"{value:,.2f}"
        formatted = s.replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        formatted = f"{value:,.2f}"

    if symbol:
        sep = " " if currency_code == "BRL" else ""
        return f"{symbol}{sep}{formatted}"

    if lang == "ja":
        return f"¥{formatted}"
    if lang == "en":
        return f"${formatted}"
    return f"R$ {formatted}"


# ---------------------------------------------------------------------------
# Category name translations (internal key → display name per language)
# Internal keys are the Portuguese names stored in the database.
# ---------------------------------------------------------------------------

CATEGORY_NAMES: dict[str, dict[str, str]] = {
    "pt": {
        "Alimentação": "Alimentação",
        "Refeição": "Refeição",
        "Transporte": "Transporte",
        "Moradia": "Moradia",
        "Saúde": "Saúde",
        "Educação": "Educação",
        "Lazer": "Lazer",
        "Vestuário": "Vestuário",
        "Outros": "Outros",
        "Salário": "Salário",
        "Freelance": "Freelance",
        "Investimento": "Investimento",
        "Presente": "Presente",
        "Renda Extra": "Renda Extra",
    },
    "en": {
        "Alimentação": "Groceries",
        "Refeição": "Meals",
        "Transporte": "Transport",
        "Moradia": "Housing",
        "Saúde": "Health",
        "Educação": "Education",
        "Lazer": "Leisure",
        "Vestuário": "Clothing",
        "Outros": "Other",
        "Salário": "Salary",
        "Freelance": "Freelance",
        "Investimento": "Investment",
        "Presente": "Gift",
        "Renda Extra": "Extra Income",
    },
    "ja": {
        "Alimentação": "食料品",
        "Refeição": "食事",
        "Transporte": "交通",
        "Moradia": "住居",
        "Saúde": "健康",
        "Educação": "教育",
        "Lazer": "娯楽",
        "Vestuário": "衣類",
        "Outros": "その他",
        "Salário": "給料",
        "Freelance": "フリーランス",
        "Investimento": "投資",
        "Presente": "贈り物",
        "Renda Extra": "臨時収入",
    },
}


def cat_name(internal_key: str, lang: str = "pt") -> str:
    """Translate an internal category key to a display name for the given language."""
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    return CATEGORY_NAMES.get(lang, CATEGORY_NAMES["pt"]).get(internal_key, internal_key)


# ---------------------------------------------------------------------------
# Month names
# ---------------------------------------------------------------------------

MONTHS: dict[str, list[str]] = {
    "pt": [
        "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ],
    "en": [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ],
    "ja": [
        "", "1月", "2月", "3月", "4月", "5月", "6月",
        "7月", "8月", "9月", "10月", "11月", "12月",
    ],
}

# ---------------------------------------------------------------------------
# Greetings (words that trigger a greeting reply instead of expense parsing)
# ---------------------------------------------------------------------------

GREETINGS: dict[str, set[str]] = {
    "pt": {
        "oi", "olá", "ola", "eai", "e aí", "bom dia",
        "boa tarde", "boa noite", "start",
    },
    "en": {
        "hello", "hi", "hey", "good morning", "good afternoon",
        "good evening", "start",
    },
    "ja": {
        "こんにちは", "こんばんは", "おはよう", "おはようございます",
        "やあ", "start",
    },
}

ALL_GREETINGS: set[str] = set()
for _g in GREETINGS.values():
    ALL_GREETINGS |= _g


# ---------------------------------------------------------------------------
# Bot translations
# ---------------------------------------------------------------------------

BOT: dict[str, dict[str, str]] = {
    "pt": {
        "start": (
            "Bem-vindo! 👋\n"
            "Envie uma descrição e valor para registrar.\n"
            "\n"
            "📝 Gastos:\n"
            "  jantar 20,50\n"
            "  mercado 135,90\n"
            "\n"
            "💰 Ganhos (use + no início):\n"
            "  +salario 5000\n"
            "  +freelance 800\n"
            "\n"
            "Digite /help para ver todos os comandos."
        ),
        "help": (
            "📖 Comandos disponíveis:\n"
            "\n"
            "📝 Registrar gasto:\n"
            "  Envie: <descrição> <valor>\n"
            "  Ex: jantar 20,50\n"
            "\n"
            "💰 Registrar ganho:\n"
            "  Envie: +<descrição> <valor>\n"
            "  Ex: +salario 5000\n"
            "\n"
            "📋 Consultar:\n"
            "  /today — hoje\n"
            "  /week — semana\n"
            "  /month — mês\n"
            "\n"
            "📊 Resumo:\n"
            "  /summary — resumo por categoria (mês atual)\n"
            "\n"
            "✏️ Editar / Apagar:\n"
            "  /delete <id> — apagar um registro\n"
            "  /edit <id> <valor> — editar valor\n"
            "\n"
            "🔑 Painel web:\n"
            "  /setpassword <senha> — definir senha do dashboard\n"
            "  {dashboard_url}\n"
            "\n"
            "🔄 Recorrentes:\n"
            "  /recurring — listar recorrentes\n"
            "  /addrecurring — criar nova\n"
            "  /delrecurring — excluir\n"
            "\n"
            "📤 Exportar:\n"
            "  /export — exportar CSV + PDF\n"
            "\n"
            "⚙️ Configurações:\n"
            "  /config — ver configurações atuais\n"
            "  /lang — idioma\n"
            "  /setcurrency — moeda padrão\n"
            "  /settimezone — fuso horário"
        ),
        "greeting": (
            "Olá! 👋\n"
            "Gasto: <descrição> <valor> (ex: jantar 20,50)\n"
            "Ganho: +<descrição> <valor> (ex: +salario 5000)\n"
            "\n"
            "Digite /help para ver todos os comandos."
        ),
        "invalid": (
            "Formato inválido.\n"
            "Gasto: <descrição> <valor> (ex: jantar 20,50)\n"
            "Ganho: +<descrição> <valor> (ex: +salario 5000)"
        ),
        "stored_expense": "🔴 #{id} Gasto: {description} — {value} [{category}]",
        "stored_income": "🟢 #{id} Ganho: {description} — {value} [{category}]",
        "deleted": "🗑️ Gasto #{id} apagado.",
        "delete_not_found": "Gasto #{id} não encontrado (ou não pertence a você).",
        "delete_usage": "Use: /delete <id>\nExemplo: /delete 5",
        "edited": "✏️ Gasto #{id} atualizado para {value}.",
        "edit_not_found": "Gasto #{id} não encontrado (ou não pertence a você).",
        "edit_usage": "Use: /edit <id> <novo_valor>\nExemplo: /edit 5 25,50",
        "no_expenses": "Nenhum gasto encontrado neste período.",
        "unauthorized": "⛔ Você não está autorizado a usar este bot.",
        "error": "Ocorreu um erro interno. Tente novamente.",
        "password_set": (
            "🔑 Senha do painel definida com sucesso!\n"
            "Acesse o dashboard: {dashboard_url}"
        ),
        "password_too_short": "Senha muito curta. Use pelo menos 4 caracteres.",
        "password_usage": "Use: /setpassword <sua_senha>\nExemplo: /setpassword minha123",
        "admin_granted": "🛡️ Você agora é admin do painel!",
        "admin_revoked": "🛡️ Privilégio de admin removido.",
        "admin_not_allowed": "⛔ Apenas o dono do bot pode usar este comando.",
        "lang_set": "🌐 Idioma alterado para Português.",
        "lang_prompt": "🌐 Escolha seu idioma / Choose your language / 言語を選択:",
        "config_title": "⚙️ Suas configurações:",
        "config_lang": "🌐 Idioma: {value}",
        "config_currency": "💱 Moeda padrão: {value}",
        "config_timezone": "🕐 Fuso horário: {value}",
        "config_hint": "Use /setcurrency, /settimezone ou /lang para alterar.",
        "setcurrency_prompt": "💱 Escolha sua moeda padrão:",
        "setcurrency_done": "💱 Moeda padrão alterada para {currency}.",
        "settimezone_prompt": "🕐 Escolha seu fuso horário:",
        "settimezone_done": "🕐 Fuso horário alterado para {timezone}.",
        "currency_converted": "  ≈ {converted} ({rate})",
        "recurring_title": "🔄 Suas transações recorrentes:",
        "recurring_empty": "Nenhuma transação recorrente cadastrada.",
        "recurring_item": "  #{id} {icon} {description} — {amount} [{category}] (dia {day}, {status})",
        "recurring_active": "ativo",
        "recurring_paused": "pausado",
        "addrecurring_usage": (
            "Use: /addrecurring <descrição> <valor> [dia]\n"
            "Exemplo: /addrecurring aluguel 1500 5\n"
            "Ganho: /addrecurring +salario 5000 1"
        ),
        "addrecurring_done": "🔄 Recorrente #{id} criada: {description} — {amount} (dia {day})",
        "delrecurring_usage": "Use: /delrecurring <id>\nExemplo: /delrecurring 1",
        "delrecurring_done": "🗑️ Recorrente #{id} removida.",
        "delrecurring_not_found": "Recorrente #{id} não encontrada.",
        "togglerecurring_usage": "Use: /togglerecurring <id>\nExemplo: /togglerecurring 1",
        "togglerecurring_done": "🔄 Recorrente #{id} agora está {status}.",
        "recurring_executed": "🔄 Transação automática #{tx_id}: {description} — {amount}",
        "export_usage": "Use: /export [período]\nPeríodos: today, week, month (padrão: month)",
        "export_empty": "Nenhum registro encontrado para exportar neste período.",
        "export_csv_caption": "📊 Exportação CSV — {period}",
        "export_pdf_caption": "📊 Exportação PDF — {period}",
        "backdated": "📅 Registrado em {date}",
        "low_confidence": "🤔 Categoria: [{category}] (não tenho certeza)\nToque para corrigir:",
        "category_corrected": "✅ Categoria do #{id} alterada para [{category}].",
        "today_title": "📋 Hoje ({date})",
        "week_title": "📋 Semana",
        "month_title": "📋 {month}/{year}",
        "summary_title": "📊 Resumo de {month}/{year}",
        "balance": "Saldo",
        "total_income": "Total Ganhos",
        "total_expenses": "Total Gastos",
        "link_invalid": "🔗 Código inválido ou expirado. Gere um novo no painel web.",
        "link_already_taken": "🔗 Esta conta do Telegram já está vinculada a outro usuário do site.",
        "link_success": "🔗 Telegram vinculado com sucesso! Suas transações agora ficam acessíveis no site.",
        "admin_user_not_found": "Usuário do Telegram não encontrado.",
    },
    "en": {
        "start": (
            "Welcome! 👋\n"
            "Send a description and amount to log a transaction.\n"
            "\n"
            "📝 Expenses:\n"
            "  dinner 20.50\n"
            "  groceries 135.90\n"
            "\n"
            "💰 Income (use + prefix):\n"
            "  +salary 5000\n"
            "  +freelance 800\n"
            "\n"
            "Type /help to see all commands."
        ),
        "help": (
            "📖 Available commands:\n"
            "\n"
            "📝 Log expense:\n"
            "  Send: <description> <amount>\n"
            "  Ex: dinner 20.50\n"
            "\n"
            "💰 Log income:\n"
            "  Send: +<description> <amount>\n"
            "  Ex: +salary 5000\n"
            "\n"
            "📋 View:\n"
            "  /today — today\n"
            "  /week — this week\n"
            "  /month — this month\n"
            "\n"
            "📊 Summary:\n"
            "  /summary — category breakdown (current month)\n"
            "\n"
            "✏️ Edit / Delete:\n"
            "  /delete <id> — delete a record\n"
            "  /edit <id> <amount> — edit amount\n"
            "\n"
            "🔑 Web dashboard:\n"
            "  /setpassword <pass> — set dashboard password\n"
            "  {dashboard_url}\n"
            "\n"
            "🔄 Recurring:\n"
            "  /recurring — list recurring\n"
            "  /addrecurring — create new\n"
            "  /delrecurring — delete\n"
            "\n"
            "📤 Export:\n"
            "  /export — export CSV + PDF\n"
            "\n"
            "⚙️ Settings:\n"
            "  /config — view current settings\n"
            "  /lang — language\n"
            "  /setcurrency — default currency\n"
            "  /settimezone — timezone"
        ),
        "greeting": (
            "Hello! 👋\n"
            "Expense: <description> <amount> (e.g. dinner 20.50)\n"
            "Income: +<description> <amount> (e.g. +salary 5000)\n"
            "\n"
            "Type /help to see all commands."
        ),
        "invalid": (
            "Invalid format.\n"
            "Expense: <description> <amount> (e.g. dinner 20.50)\n"
            "Income: +<description> <amount> (e.g. +salary 5000)"
        ),
        "stored_expense": "🔴 #{id} Expense: {description} — {value} [{category}]",
        "stored_income": "🟢 #{id} Income: {description} — {value} [{category}]",
        "deleted": "🗑️ Record #{id} deleted.",
        "delete_not_found": "Record #{id} not found (or doesn't belong to you).",
        "delete_usage": "Use: /delete <id>\nExample: /delete 5",
        "edited": "✏️ Record #{id} updated to {value}.",
        "edit_not_found": "Record #{id} not found (or doesn't belong to you).",
        "edit_usage": "Use: /edit <id> <new_amount>\nExample: /edit 5 25.50",
        "no_expenses": "No records found for this period.",
        "unauthorized": "⛔ You are not authorized to use this bot.",
        "error": "An internal error occurred. Please try again.",
        "password_set": (
            "🔑 Dashboard password set successfully!\n"
            "Access the dashboard: {dashboard_url}"
        ),
        "password_too_short": "Password too short. Use at least 4 characters.",
        "password_usage": "Use: /setpassword <your_password>\nExample: /setpassword mypass123",
        "admin_granted": "🛡️ You are now a dashboard admin!",
        "admin_revoked": "🛡️ Admin privilege removed.",
        "admin_not_allowed": "⛔ Only the bot owner can use this command.",
        "lang_set": "🌐 Language changed to English.",
        "lang_prompt": "🌐 Escolha seu idioma / Choose your language / 言語を選択:",
        "config_title": "⚙️ Your settings:",
        "config_lang": "🌐 Language: {value}",
        "config_currency": "💱 Default currency: {value}",
        "config_timezone": "🕐 Timezone: {value}",
        "config_hint": "Use /setcurrency, /settimezone or /lang to change.",
        "setcurrency_prompt": "💱 Choose your default currency:",
        "setcurrency_done": "💱 Default currency changed to {currency}.",
        "settimezone_prompt": "🕐 Choose your timezone:",
        "settimezone_done": "🕐 Timezone changed to {timezone}.",
        "currency_converted": "  ≈ {converted} ({rate})",
        "recurring_title": "🔄 Your recurring transactions:",
        "recurring_empty": "No recurring transactions set up.",
        "recurring_item": "  #{id} {icon} {description} — {amount} [{category}] (day {day}, {status})",
        "recurring_active": "active",
        "recurring_paused": "paused",
        "addrecurring_usage": (
            "Use: /addrecurring <description> <amount> [day]\n"
            "Example: /addrecurring rent 1500 5\n"
            "Income: /addrecurring +salary 5000 1"
        ),
        "addrecurring_done": "🔄 Recurring #{id} created: {description} — {amount} (day {day})",
        "delrecurring_usage": "Use: /delrecurring <id>\nExample: /delrecurring 1",
        "delrecurring_done": "🗑️ Recurring #{id} removed.",
        "delrecurring_not_found": "Recurring #{id} not found.",
        "togglerecurring_usage": "Use: /togglerecurring <id>\nExample: /togglerecurring 1",
        "togglerecurring_done": "🔄 Recurring #{id} is now {status}.",
        "recurring_executed": "🔄 Auto-transaction #{tx_id}: {description} — {amount}",
        "export_usage": "Use: /export [period]\nPeriods: today, week, month (default: month)",
        "export_empty": "No records found to export for this period.",
        "export_csv_caption": "📊 CSV Export — {period}",
        "export_pdf_caption": "📊 PDF Export — {period}",
        "backdated": "📅 Recorded on {date}",
        "low_confidence": "🤔 Category: [{category}] (not sure)\nTap to correct:",
        "category_corrected": "✅ Category for #{id} changed to [{category}].",
        "today_title": "📋 Today ({date})",
        "week_title": "📋 This Week",
        "month_title": "📋 {month}/{year}",
        "summary_title": "📊 Summary for {month}/{year}",
        "balance": "Balance",
        "total_income": "Total Income",
        "total_expenses": "Total Expenses",
        "link_invalid": "🔗 Invalid or expired code. Generate a new one on the web dashboard.",
        "link_already_taken": "🔗 This Telegram account is already linked to another web user.",
        "link_success": "🔗 Telegram linked successfully! Your transactions are now accessible on the web.",
        "admin_user_not_found": "Telegram user not found.",
    },
    "ja": {
        "start": (
            "ようこそ！ 👋\n"
            "説明と金額を送信して記録してください。\n"
            "\n"
            "📝 支出:\n"
            "  夕食 2050\n"
            "  スーパー 13590\n"
            "\n"
            "💰 収入（+を付ける）:\n"
            "  +給料 300000\n"
            "  +副業 50000\n"
            "\n"
            "/help でコマンド一覧を表示"
        ),
        "help": (
            "📖 コマンド一覧:\n"
            "\n"
            "📝 支出を記録:\n"
            "  送信: <説明> <金額>\n"
            "  例: 夕食 2050\n"
            "\n"
            "💰 収入を記録:\n"
            "  送信: +<説明> <金額>\n"
            "  例: +給料 300000\n"
            "\n"
            "📋 表示:\n"
            "  /today — 今日\n"
            "  /week — 今週\n"
            "  /month — 今月\n"
            "\n"
            "📊 集計:\n"
            "  /summary — カテゴリ別集計（今月）\n"
            "\n"
            "✏️ 編集 / 削除:\n"
            "  /delete <id> — 記録を削除\n"
            "  /edit <id> <金額> — 金額を編集\n"
            "\n"
            "🔑 ダッシュボード:\n"
            "  /setpassword <パスワード> — パスワード設定\n"
            "  {dashboard_url}\n"
            "\n"
            "🔄 定期取引:\n"
            "  /recurring — 一覧表示\n"
            "  /addrecurring — 新規作成\n"
            "  /delrecurring — 削除\n"
            "\n"
            "📤 エクスポート:\n"
            "  /export — CSV + PDFエクスポート\n"
            "\n"
            "⚙️ 設定:\n"
            "  /config — 現在の設定を表示\n"
            "  /lang — 言語\n"
            "  /setcurrency — デフォルト通貨\n"
            "  /settimezone — タイムゾーン"
        ),
        "greeting": (
            "こんにちは！ 👋\n"
            "支出: <説明> <金額>（例: 夕食 2050）\n"
            "収入: +<説明> <金額>（例: +給料 300000）\n"
            "\n"
            "/help でコマンド一覧を表示"
        ),
        "invalid": (
            "形式が正しくありません。\n"
            "支出: <説明> <金額>（例: 夕食 2050）\n"
            "収入: +<説明> <金額>（例: +給料 300000）"
        ),
        "stored_expense": "🔴 #{id} 支出: {description} — {value} [{category}]",
        "stored_income": "🟢 #{id} 収入: {description} — {value} [{category}]",
        "deleted": "🗑️ 記録 #{id} を削除しました。",
        "delete_not_found": "記録 #{id} が見つかりません（またはあなたのものではありません）。",
        "delete_usage": "使い方: /delete <id>\n例: /delete 5",
        "edited": "✏️ 記録 #{id} を {value} に更新しました。",
        "edit_not_found": "記録 #{id} が見つかりません（またはあなたのものではありません）。",
        "edit_usage": "使い方: /edit <id> <新しい金額>\n例: /edit 5 2550",
        "no_expenses": "この期間の記録はありません。",
        "unauthorized": "⛔ このボットの使用権限がありません。",
        "error": "内部エラーが発生しました。もう一度お試しください。",
        "password_set": (
            "🔑 ダッシュボードのパスワードを設定しました！\n"
            "ダッシュボード: {dashboard_url}"
        ),
        "password_too_short": "パスワードが短すぎます。4文字以上にしてください。",
        "password_usage": "使い方: /setpassword <パスワード>\n例: /setpassword mypass123",
        "admin_granted": "🛡️ ダッシュボード管理者になりました！",
        "admin_revoked": "🛡️ 管理者権限が削除されました。",
        "admin_not_allowed": "⛔ このコマンドはボットのオーナーのみ使用できます。",
        "lang_set": "🌐 言語を日本語に変更しました。",
        "lang_prompt": "🌐 Escolha seu idioma / Choose your language / 言語を選択:",
        "config_title": "⚙️ 現在の設定:",
        "config_lang": "🌐 言語: {value}",
        "config_currency": "💱 デフォルト通貨: {value}",
        "config_timezone": "🕐 タイムゾーン: {value}",
        "config_hint": "/setcurrency, /settimezone, /lang で変更できます。",
        "setcurrency_prompt": "💱 デフォルト通貨を選んでください:",
        "setcurrency_done": "💱 デフォルト通貨を {currency} に変更しました。",
        "settimezone_prompt": "🕐 タイムゾーンを選んでください:",
        "settimezone_done": "🕐 タイムゾーンを {timezone} に変更しました。",
        "currency_converted": "  ≈ {converted} ({rate})",
        "recurring_title": "🔄 定期取引一覧:",
        "recurring_empty": "定期取引は登録されていません。",
        "recurring_item": "  #{id} {icon} {description} — {amount} [{category}] ({day}日, {status})",
        "recurring_active": "有効",
        "recurring_paused": "一時停止",
        "addrecurring_usage": (
            "使い方: /addrecurring <説明> <金額> [日]\n"
            "例: /addrecurring 家賃 150000 5\n"
            "収入: /addrecurring +給料 300000 1"
        ),
        "addrecurring_done": "🔄 定期 #{id} 作成: {description} — {amount} ({day}日)",
        "delrecurring_usage": "使い方: /delrecurring <id>\n例: /delrecurring 1",
        "delrecurring_done": "🗑️ 定期 #{id} を削除しました。",
        "delrecurring_not_found": "定期 #{id} が見つかりません。",
        "togglerecurring_usage": "使い方: /togglerecurring <id>\n例: /togglerecurring 1",
        "togglerecurring_done": "🔄 定期 #{id} は{status}になりました。",
        "recurring_executed": "🔄 自動取引 #{tx_id}: {description} — {amount}",
        "export_usage": "使い方: /export [期間]\n期間: today, week, month (デフォルト: month)",
        "export_empty": "この期間のエクスポート対象がありません。",
        "export_csv_caption": "📊 CSVエクスポート — {period}",
        "export_pdf_caption": "📊 PDFエクスポート — {period}",
        "backdated": "📅 {date}に記録",
        "low_confidence": "🤔 カテゴリ: [{category}]（不確か）\nタップして修正:",
        "category_corrected": "✅ #{id} のカテゴリを [{category}] に変更しました。",
        "today_title": "📋 今日 ({date})",
        "week_title": "📋 今週",
        "month_title": "📋 {year}年{month}",
        "summary_title": "📊 {year}年{month}の集計",
        "balance": "残高",
        "total_income": "収入合計",
        "total_expenses": "支出合計",
        "link_invalid": "🔗 コードが無効または期限切れです。Webダッシュボードで新しいコードを生成してください。",
        "link_already_taken": "🔗 このTelegramアカウントは既に他のWebユーザーにリンクされています。",
        "link_success": "🔗 Telegramのリンクに成功しました！取引がWebでアクセス可能になりました。",
        "admin_user_not_found": "Telegramユーザーが見つかりません。",
    },
}


# ---------------------------------------------------------------------------
# Dashboard translations
# ---------------------------------------------------------------------------

DASH: dict[str, dict[str, str]] = {
    "pt": {
        "page_title": "Finance",
        "landing_tagline": "Suas finanças, organizadas em segundos",
        "landing_hero_title": "Controle financeiro que cabe num bate-papo",
        "landing_hero_subtitle": (
            "Registre gastos e receitas conversando, em qualquer idioma e moeda. "
            "Veja seu painel atualizado em tempo real, no celular ou no computador."
        ),
        "landing_cta_primary": "Criar conta grátis",
        "landing_cta_secondary": "Já tenho conta",
        "landing_cta_title": "Comece a organizar agora",
        "landing_cta_subtitle": "30 segundos. Sem cartão. Sem complicação.",
        "footer_tagline": "Finanças simples e privadas",
        "feature_chat_title": "Chat natural",
        "feature_chat_body": "Digite \"jantar 30\" ou \"+salário 5000\" e pronto. Categorização automática.",
        "feature_dashboard_title": "Painel completo",
        "feature_dashboard_body": "Gráficos, comparativo mensal, top categorias, busca e exportação CSV/PDF.",
        "feature_multicurrency_title": "Multi-moeda",
        "feature_multicurrency_body": "BRL, USD, EUR, JPY, GBP. Conversão automática para sua moeda padrão.",
        "feature_telegram_title": "Telegram opcional",
        "feature_telegram_body": "Vincule seu Telegram depois e registre gastos por mensagem quando quiser.",
        "feature_recurring_title": "Recorrentes",
        "feature_recurring_body": "Aluguel, salário, assinaturas: configure uma vez e o app cuida do resto.",
        "feature_export_title": "Exportar tudo",
        "feature_export_body": "CSV ou PDF do período que quiser, sem amarras.",
        "nav_login": "Entrar",
        "nav_signup": "Criar conta",
        "nav_logout": "Sair",
        "nav_app": "Início",
        "nav_dashboard": "Painel",
        "nav_recurring": "Recorrentes",
        "nav_settings": "Ajustes",
        "nav_admin": "Admin",
        "signup_title": "Criar sua conta",
        "signup_subtitle": "30 segundos para começar",
        "signup_have_account": "Já tem conta?",
        "signup_username": "Usuário",
        "signup_email": "E-mail (opcional)",
        "signup_email_hint": "Permite recuperar acesso e fazer login pelo e-mail.",
        "signup_password": "Senha",
        "signup_password_confirm": "Confirme a senha",
        "signup_lang": "Idioma",
        "signup_currency": "Moeda padrão",
        "signup_submit": "Criar conta",
        "signup_telegram_hint": "Você poderá vincular seu Telegram depois nos ajustes.",
        "signup_err_username_length": "Use entre 3 e 32 caracteres.",
        "signup_err_username_chars": "Apenas letras, números, _ e -.",
        "signup_err_username_taken": "Este usuário já existe.",
        "signup_err_email_invalid": "E-mail inválido.",
        "signup_err_email_taken": "Este e-mail já está em uso.",
        "signup_err_password_short": "Senha precisa ter ao menos 6 caracteres.",
        "signup_err_password_mismatch": "As senhas não coincidem.",
        "login_title_page": "Bem-vindo de volta",
        "login_subtitle": "Entre para acessar suas finanças",
        "login_identifier": "Usuário ou e-mail",
        "login_no_account": "Não tem conta?",
        "login_err_invalid": "Credenciais inválidas.",
        "settings_title_page": "Ajustes",
        "settings_caption": "Idioma, moeda, fuso horário e vínculo com Telegram",
        "settings_preferences": "Preferências",
        "settings_save": "Salvar",
        "settings_password_saved": "Senha alterada com sucesso.",
        "settings_email_saved": "E-mail atualizado com sucesso.",
        "settings_email_title": "E-mail",
        "settings_email_caption": "Usado para login e recuperação de acesso.",
        "settings_unlinked": "Telegram desvinculado.",
        "email_label": "E-mail",
        "email_setup_title": "Confirme seu e-mail",
        "email_setup_subtitle": "Precisamos do seu e-mail antes de continuar.",
        "email_setup_why": "Seu e-mail é usado para login alternativo e recuperação de acesso. Levamos só 10 segundos.",
        "email_setup_submit": "Salvar e-mail",
        "settings_telegram_title": "Telegram",
        "settings_telegram_caption": "Registre gastos pelo Telegram além do site (opcional).",
        "settings_telegram_linked": "Telegram vinculado (id {id}).",
        "settings_telegram_link": "Vincular Telegram",
        "settings_telegram_unlink": "Desvincular",
        "settings_change_password": "Alterar senha",
        "settings_current_password": "Senha atual",
        "settings_new_password": "Nova senha",
        "settings_err_wrong_password": "Senha atual incorreta.",
        "settings_danger_zone": "Zona de perigo",
        "settings_delete_caption": "Excluir conta apaga todas as suas transações e recorrentes. Não tem volta.",
        "settings_delete_placeholder": "Digite \"{username}\" para confirmar",
        "settings_delete_button": "Excluir conta",
        "settings_delete_confirm_js": "Tem certeza? Esta ação não pode ser desfeita.",
        "settings_err_delete_confirm": "Confirmação não bate com seu usuário.",
        "link_telegram_title": "Vincular Telegram",
        "link_telegram_subtitle": "Use o código abaixo no bot",
        "link_telegram_code_label": "Seu código",
        "link_telegram_expires": "Válido por 10 minutos",
        "link_telegram_step1": "1. Abra o bot no Telegram",
        "link_telegram_open_bot": "Abrir @{bot}",
        "link_telegram_manual": "Abra o seu bot no Telegram e envie a mensagem: /start link_{code}",
        "link_telegram_step2": "2. Confirme o código",
        "link_telegram_step2_body": "O link já vem com o código pronto. Basta clicar em iniciar.",
        "link_telegram_back": "← Voltar para Ajustes",
        "error_404_title": "Página não encontrada",
        "error_404_body": "O link pode estar quebrado ou a página foi movida.",
        "error_back_home": "Voltar ao início",
        "app_title": "Meu Painel",
        "app_recent": "Atividade recente",
        "app_empty_title": "Sem registros ainda.",
        "app_empty_hint": "Digite \"jantar 30\" abaixo para começar.",
        "app_chat_placeholder": "ex: jantar 30 ou +salário 5000",
        "app_chat_send": "Enviar",
        "app_chat_hint": "Use + para receitas. Inclua a moeda (\"30 usd\") ou data (\"ontem\") quando precisar.",
        "app_delete_confirm": "Apagar este registro?",
        "app_low_confidence": "Categoria incerta. Corrigir para:",
        "app_backdated": "📅 Registrado em {date}",
        "recurring_add_title": "Nova recorrente",
        "recurring_add_button": "Criar",
        "recurring_list_title": "Suas recorrentes",
        "recurring_empty_state": "Nenhuma recorrente cadastrada ainda.",
        "recurring_added": "✅ Recorrente criada.",
        "recurring_toggled": "🔄 Status atualizado.",
        "recurring_deleted": "🗑️ Recorrente removida.",
        "recurring_toggle": "Pausar/Retomar",
        "recurring_delete": "Remover",
        "recurring_delete_confirm": "Remover esta recorrente?",
        "recurring_day_label": "dia {day}",
        "page_title_dashboard": "Finance Dashboard",
        "login_title": "💰 Finance Dashboard",
        "login_caption": "Faça login com seu usuário do Telegram e a senha definida via /setpassword",
        "login_username": "Usuário do Telegram",
        "login_password": "Senha",
        "login_submit": "Entrar",
        "login_empty": "Preencha todos os campos.",
        "login_invalid": "Usuário ou senha inválidos. Defina sua senha no bot com /setpassword",
        "sidebar_caption": "Painel de controle financeiro",
        "sidebar_logout": "🚪 Sair",
        "sidebar_period": "📅 Período",
        "sidebar_quick": "⏱️ Atalhos",
        "quick_today": "Hoje",
        "quick_week": "Semana",
        "quick_month": "Mês",
        "quick_last_month": "Mês Anterior",
        "quick_3months": "3 Meses",
        "quick_6months": "6 Meses",
        "quick_year": "Ano",
        "quick_custom": "Personalizar",
        "sidebar_categories": "🏷️ Categorias",
        "sidebar_period_label": "Período",
        "sidebar_records": "Registros",
        "sidebar_lang": "🌐 Idioma",
        "title": "💰 Painel Financeiro — {period}",
        "no_data": "Nenhum registro encontrado no período selecionado. Registre pelo bot do Telegram!",
        "comparison_title": "📊 Comparativo com Período Anterior",
        "prev_period": "Período anterior: {start} — {end}",
        "current_period_label": "Atual",
        "previous_period_label": "Anterior",
        "delta_expenses": "Gastos",
        "delta_income": "Ganhos",
        "delta_balance": "Saldo",
        "delta_tx": "Transações",
        "no_prev_data": "Sem dados do período anterior para comparar.",
        "kpi_total": "Total Gastos",
        "kpi_income": "Total Ganhos",
        "kpi_balance": "Saldo",
        "kpi_tx": "Transações",
        "kpi_top": "Top Categoria",
        "sidebar_type": "📊 Tipo",
        "type_all": "Todos",
        "type_expense": "Gastos",
        "type_income": "Ganhos",
        "col_type": "Tipo",
        "chart_timeline": "📈 Movimentação ao Longo do Tempo",
        "chart_donut": "🍩 Distribuição por Categoria",
        "chart_bar": "📊 Gastos por Categoria",
        "chart_cumulative": "📉 Acumulado no Período",
        "chart_monthly": "📅 Comparativo Mensal (últimos 12 meses)",
        "chart_no_history": "Sem dados históricos de meses anteriores.",
        "top_expenses": "🔝 Maiores Gastos do Período",
        "all_tx": "📋 Todas as Transações",
        "search": "🔍 Buscar por descrição",
        "showing": "Mostrando {shown} de {total} registros",
        "col_id": "ID",
        "col_datetime": "Data/Hora",
        "col_desc": "Descrição",
        "col_value": "Valor",
        "col_category": "Categoria",
        "currency_axis": "R$",
        "cumulative_axis": "R$ (acumulado)",
        "admin_title": "🛡️ Painel Admin",
        "admin_kpi_users": "Usuários",
        "admin_kpi_active7": "Ativos (7d)",
        "admin_kpi_active30": "Ativos (30d)",
        "admin_kpi_total_tx": "Total Transações",
        "admin_users_table": "👥 Usuários",
        "admin_col_user": "Usuário",
        "admin_col_lang": "Idioma",
        "admin_col_tx": "Transações",
        "admin_col_expenses": "Gastos",
        "admin_col_income": "Ganhos",
        "admin_col_balance": "Saldo",
        "admin_col_first": "Primeira Atividade",
        "admin_col_last": "Última Atividade",
        "admin_chart_daily": "📈 Atividade Diária da Plataforma",
        "admin_chart_users": "👥 Usuários Ativos por Dia",
        "admin_no_data": "Nenhum dado na plataforma ainda.",
        "admin_switch_personal": "👤 Meu Painel",
        "admin_switch_admin": "🛡️ Painel Admin",
        "settings_title": "⚙️ Configurações",
        "settings_currency": "💱 Moeda Padrão",
        "settings_timezone": "🕐 Fuso Horário",
        "settings_saved": "✅ Configurações salvas!",
        "export_csv": "📥 Exportar CSV",
        "export_pdf": "📥 Exportar PDF",
        "sidebar_currency_filter": "💱 Moeda",
        "currency_all": "Todas",
        "col_currency": "Moeda",
        "recurring_title": "🔄 Recorrentes",
        "recurring_col_desc": "Descrição",
        "recurring_col_amount": "Valor",
        "recurring_col_day": "Dia",
        "recurring_col_status": "Status",
        "recurring_col_next": "Próximo",
        "recurring_active": "Ativo",
        "recurring_paused": "Pausado",
    },
    "en": {
        "page_title": "Finance",
        "landing_tagline": "Your finances, organized in seconds",
        "landing_hero_title": "Money tracking that fits in a chat",
        "landing_hero_subtitle": (
            "Log expenses and income in plain words, in any language and currency. "
            "Watch your dashboard update live, on phone or desktop."
        ),
        "landing_cta_primary": "Sign up free",
        "landing_cta_secondary": "I have an account",
        "landing_cta_title": "Start tracking now",
        "landing_cta_subtitle": "30 seconds. No card. No friction.",
        "footer_tagline": "Simple, private personal finance",
        "feature_chat_title": "Natural chat",
        "feature_chat_body": "Type \"dinner 30\" or \"+salary 5000\". Auto-categorized instantly.",
        "feature_dashboard_title": "Full dashboard",
        "feature_dashboard_body": "Charts, monthly comparison, top categories, search and CSV/PDF export.",
        "feature_multicurrency_title": "Multi-currency",
        "feature_multicurrency_body": "BRL, USD, EUR, JPY, GBP. Auto conversion to your default currency.",
        "feature_telegram_title": "Optional Telegram",
        "feature_telegram_body": "Link Telegram later and log on the go via chat messages.",
        "feature_recurring_title": "Recurring",
        "feature_recurring_body": "Rent, salary, subscriptions: set once, forget about it.",
        "feature_export_title": "Export anything",
        "feature_export_body": "CSV or PDF for any period, no lock-in.",
        "nav_login": "Log in",
        "nav_signup": "Sign up",
        "nav_logout": "Log out",
        "nav_app": "Home",
        "nav_dashboard": "Dashboard",
        "nav_recurring": "Recurring",
        "nav_settings": "Settings",
        "nav_admin": "Admin",
        "signup_title": "Create your account",
        "signup_subtitle": "30 seconds to get started",
        "signup_have_account": "Have an account?",
        "signup_username": "Username",
        "signup_email": "Email (optional)",
        "signup_email_hint": "Lets you recover access and sign in with your email.",
        "signup_password": "Password",
        "signup_password_confirm": "Confirm password",
        "signup_lang": "Language",
        "signup_currency": "Default currency",
        "signup_submit": "Create account",
        "signup_telegram_hint": "You can link your Telegram later in Settings.",
        "signup_err_username_length": "Use 3 to 32 characters.",
        "signup_err_username_chars": "Only letters, numbers, _ and -.",
        "signup_err_username_taken": "Username already taken.",
        "signup_err_email_invalid": "Invalid email.",
        "signup_err_email_taken": "This email is already in use.",
        "signup_err_password_short": "Password must be at least 6 characters.",
        "signup_err_password_mismatch": "Passwords do not match.",
        "login_title_page": "Welcome back",
        "login_subtitle": "Sign in to access your finances",
        "login_identifier": "Username or email",
        "login_no_account": "Don't have an account?",
        "login_err_invalid": "Invalid credentials.",
        "settings_title_page": "Settings",
        "settings_caption": "Language, currency, timezone, and Telegram link",
        "settings_preferences": "Preferences",
        "settings_save": "Save",
        "settings_password_saved": "Password updated.",
        "settings_email_saved": "Email updated.",
        "settings_email_title": "Email",
        "settings_email_caption": "Used for sign-in and account recovery.",
        "settings_unlinked": "Telegram unlinked.",
        "email_label": "Email",
        "email_setup_title": "Confirm your email",
        "email_setup_subtitle": "We need your email before you continue.",
        "email_setup_why": "Your email is used for alternative sign-in and account recovery. Takes 10 seconds.",
        "email_setup_submit": "Save email",
        "settings_telegram_title": "Telegram",
        "settings_telegram_caption": "Optionally log expenses via Telegram in addition to the web.",
        "settings_telegram_linked": "Telegram linked (id {id}).",
        "settings_telegram_link": "Link Telegram",
        "settings_telegram_unlink": "Unlink",
        "settings_change_password": "Change password",
        "settings_current_password": "Current password",
        "settings_new_password": "New password",
        "settings_err_wrong_password": "Current password is incorrect.",
        "settings_danger_zone": "Danger zone",
        "settings_delete_caption": "Deleting your account permanently removes all transactions and recurring rules.",
        "settings_delete_placeholder": "Type \"{username}\" to confirm",
        "settings_delete_button": "Delete account",
        "settings_delete_confirm_js": "Are you sure? This cannot be undone.",
        "settings_err_delete_confirm": "Confirmation does not match your username.",
        "link_telegram_title": "Link Telegram",
        "link_telegram_subtitle": "Use the code below in the bot",
        "link_telegram_code_label": "Your code",
        "link_telegram_expires": "Valid for 10 minutes",
        "link_telegram_step1": "1. Open the bot in Telegram",
        "link_telegram_open_bot": "Open @{bot}",
        "link_telegram_manual": "Open your bot in Telegram and send: /start link_{code}",
        "link_telegram_step2": "2. Confirm the code",
        "link_telegram_step2_body": "The link includes the code. Just tap start.",
        "link_telegram_back": "← Back to Settings",
        "error_404_title": "Page not found",
        "error_404_body": "The link may be broken or the page was moved.",
        "error_back_home": "Back home",
        "app_title": "My Dashboard",
        "app_recent": "Recent activity",
        "app_empty_title": "No records yet.",
        "app_empty_hint": "Type \"dinner 30\" below to get started.",
        "app_chat_placeholder": "e.g. dinner 30 or +salary 5000",
        "app_chat_send": "Send",
        "app_chat_hint": "Use + for income. Add currency (\"30 usd\") or a date (\"yesterday\") when needed.",
        "app_delete_confirm": "Delete this record?",
        "app_low_confidence": "Unsure category. Change to:",
        "app_backdated": "📅 Recorded on {date}",
        "recurring_add_title": "New recurring",
        "recurring_add_button": "Create",
        "recurring_list_title": "Your recurring rules",
        "recurring_empty_state": "No recurring rules yet.",
        "recurring_added": "✅ Recurring created.",
        "recurring_toggled": "🔄 Status updated.",
        "recurring_deleted": "🗑️ Recurring removed.",
        "recurring_toggle": "Pause/Resume",
        "recurring_delete": "Remove",
        "recurring_delete_confirm": "Remove this recurring rule?",
        "recurring_day_label": "day {day}",
        "page_title_dashboard": "Finance Dashboard",
        "login_title": "💰 Finance Dashboard",
        "login_caption": "Log in with your Telegram username and the password set via /setpassword",
        "login_username": "Telegram username",
        "login_password": "Password",
        "login_submit": "Log in",
        "login_empty": "Please fill in all fields.",
        "login_invalid": "Invalid username or password. Set your password in the bot with /setpassword",
        "sidebar_caption": "Financial control panel",
        "sidebar_logout": "🚪 Log out",
        "sidebar_period": "📅 Period",
        "sidebar_quick": "⏱️ Quick Select",
        "quick_today": "Today",
        "quick_week": "Week",
        "quick_month": "Month",
        "quick_last_month": "Last Month",
        "quick_3months": "3 Months",
        "quick_6months": "6 Months",
        "quick_year": "Year",
        "quick_custom": "Custom",
        "sidebar_categories": "🏷️ Categories",
        "sidebar_period_label": "Period",
        "sidebar_records": "Records",
        "sidebar_lang": "🌐 Language",
        "title": "💰 Finance Dashboard — {period}",
        "no_data": "No records found for this period. Record transactions via the Telegram bot!",
        "comparison_title": "📊 Comparison with Previous Period",
        "prev_period": "Previous period: {start} — {end}",
        "current_period_label": "Current",
        "previous_period_label": "Previous",
        "delta_expenses": "Expenses",
        "delta_income": "Income",
        "delta_balance": "Balance",
        "delta_tx": "Transactions",
        "no_prev_data": "No previous period data to compare.",
        "kpi_total": "Total Expenses",
        "kpi_income": "Total Income",
        "kpi_balance": "Balance",
        "kpi_tx": "Transactions",
        "kpi_top": "Top Category",
        "sidebar_type": "📊 Type",
        "type_all": "All",
        "type_expense": "Expenses",
        "type_income": "Income",
        "col_type": "Type",
        "chart_timeline": "📈 Spending Over Time",
        "chart_donut": "🍩 Category Distribution",
        "chart_bar": "📊 Spending by Category",
        "chart_cumulative": "📉 Cumulative Spending",
        "chart_monthly": "📅 Monthly Comparison (last 12 months)",
        "chart_no_history": "No historical data from previous months.",
        "top_expenses": "🔝 Top Expenses",
        "all_tx": "📋 All Transactions",
        "search": "🔍 Search by description",
        "showing": "Showing {shown} of {total} records",
        "col_id": "ID",
        "col_datetime": "Date/Time",
        "col_desc": "Description",
        "col_value": "Amount",
        "col_category": "Category",
        "currency_axis": "$",
        "cumulative_axis": "$ (cumulative)",
        "admin_title": "🛡️ Admin Panel",
        "admin_kpi_users": "Users",
        "admin_kpi_active7": "Active (7d)",
        "admin_kpi_active30": "Active (30d)",
        "admin_kpi_total_tx": "Total Transactions",
        "admin_users_table": "👥 Users",
        "admin_col_user": "User",
        "admin_col_lang": "Language",
        "admin_col_tx": "Transactions",
        "admin_col_expenses": "Expenses",
        "admin_col_income": "Income",
        "admin_col_balance": "Balance",
        "admin_col_first": "First Activity",
        "admin_col_last": "Last Activity",
        "admin_chart_daily": "📈 Daily Platform Activity",
        "admin_chart_users": "👥 Active Users per Day",
        "admin_no_data": "No platform data yet.",
        "admin_switch_personal": "👤 My Dashboard",
        "admin_switch_admin": "🛡️ Admin Panel",
        "settings_title": "⚙️ Settings",
        "settings_currency": "💱 Default Currency",
        "settings_timezone": "🕐 Timezone",
        "settings_saved": "✅ Settings saved!",
        "export_csv": "📥 Export CSV",
        "export_pdf": "📥 Export PDF",
        "sidebar_currency_filter": "💱 Currency",
        "currency_all": "All",
        "col_currency": "Currency",
        "recurring_title": "🔄 Recurring",
        "recurring_col_desc": "Description",
        "recurring_col_amount": "Amount",
        "recurring_col_day": "Day",
        "recurring_col_status": "Status",
        "recurring_col_next": "Next",
        "recurring_active": "Active",
        "recurring_paused": "Paused",
    },
    "ja": {
        "page_title": "Finance",
        "landing_tagline": "数秒で整う、あなたの家計",
        "landing_hero_title": "チャットで完結する家計管理",
        "landing_hero_subtitle": "支出・収入を自然な言葉で記録。多通貨対応、リアルタイム更新、モバイルもPCも快適。",
        "landing_cta_primary": "無料で始める",
        "landing_cta_secondary": "ログイン",
        "landing_cta_title": "今すぐ始めましょう",
        "landing_cta_subtitle": "30秒。カード不要。ストレスなし。",
        "footer_tagline": "シンプルでプライベートな家計管理",
        "feature_chat_title": "自然なチャット",
        "feature_chat_body": "「夕食 2050」「+給料 300000」だけで自動分類。",
        "feature_dashboard_title": "ダッシュボード",
        "feature_dashboard_body": "グラフ、月別比較、トップカテゴリ、検索、CSV/PDF出力。",
        "feature_multicurrency_title": "多通貨",
        "feature_multicurrency_body": "BRL, USD, EUR, JPY, GBP に対応。基本通貨へ自動換算。",
        "feature_telegram_title": "Telegram連携（任意）",
        "feature_telegram_body": "後からTelegramを連携して、チャットでも記録できます。",
        "feature_recurring_title": "定期取引",
        "feature_recurring_body": "家賃、給料、定額支出を一度設定すれば自動処理。",
        "feature_export_title": "エクスポート",
        "feature_export_body": "任意の期間でCSV/PDF出力。データはあなたのもの。",
        "nav_login": "ログイン",
        "nav_signup": "登録",
        "nav_logout": "ログアウト",
        "nav_app": "ホーム",
        "nav_dashboard": "ダッシュボード",
        "nav_recurring": "定期",
        "nav_settings": "設定",
        "nav_admin": "管理",
        "signup_title": "アカウント作成",
        "signup_subtitle": "30秒で開始",
        "signup_have_account": "アカウントをお持ちですか？",
        "signup_username": "ユーザー名",
        "signup_email": "メール（任意）",
        "signup_email_hint": "アクセスの復元やメールでのログインに使えます。",
        "signup_password": "パスワード",
        "signup_password_confirm": "パスワード（確認）",
        "signup_lang": "言語",
        "signup_currency": "基本通貨",
        "signup_submit": "アカウント作成",
        "signup_telegram_hint": "Telegram連携は後から設定できます。",
        "signup_err_username_length": "3〜32文字で入力してください。",
        "signup_err_username_chars": "英数字、_、-のみ使用可能です。",
        "signup_err_username_taken": "このユーザー名は既に使用されています。",
        "signup_err_email_invalid": "メールアドレスが無効です。",
        "signup_err_email_taken": "このメールは既に使用されています。",
        "signup_err_password_short": "パスワードは6文字以上にしてください。",
        "signup_err_password_mismatch": "パスワードが一致しません。",
        "login_title_page": "おかえりなさい",
        "login_subtitle": "ログインして家計を確認",
        "login_identifier": "ユーザー名またはメール",
        "login_no_account": "アカウントをお持ちでない場合",
        "login_err_invalid": "認証情報が正しくありません。",
        "settings_title_page": "設定",
        "settings_caption": "言語・通貨・タイムゾーン・Telegram連携",
        "settings_preferences": "環境設定",
        "settings_save": "保存",
        "settings_password_saved": "パスワードを変更しました。",
        "settings_email_saved": "メールを更新しました。",
        "settings_email_title": "メール",
        "settings_email_caption": "ログインとアカウント復元に使用します。",
        "settings_unlinked": "Telegram連携を解除しました。",
        "email_label": "メール",
        "email_setup_title": "メールを確認",
        "email_setup_subtitle": "続行する前にメールアドレスが必要です。",
        "email_setup_why": "メールはログインとアカウント復元に使用します。10秒で完了します。",
        "email_setup_submit": "メールを保存",
        "settings_telegram_title": "Telegram",
        "settings_telegram_caption": "Telegramからも記録できるようにします（任意）。",
        "settings_telegram_linked": "Telegram連携済み (id {id}).",
        "settings_telegram_link": "Telegramを連携",
        "settings_telegram_unlink": "連携解除",
        "settings_change_password": "パスワードを変更",
        "settings_current_password": "現在のパスワード",
        "settings_new_password": "新しいパスワード",
        "settings_err_wrong_password": "現在のパスワードが違います。",
        "settings_danger_zone": "危険ゾーン",
        "settings_delete_caption": "アカウント削除はすべての取引と定期設定を恒久的に削除します。",
        "settings_delete_placeholder": "確認のため \"{username}\" と入力",
        "settings_delete_button": "アカウントを削除",
        "settings_delete_confirm_js": "本当によろしいですか？この操作は取り消せません。",
        "settings_err_delete_confirm": "確認文字列がユーザー名と一致しません。",
        "link_telegram_title": "Telegram連携",
        "link_telegram_subtitle": "下のコードをBotで使用",
        "link_telegram_code_label": "コード",
        "link_telegram_expires": "10分間有効",
        "link_telegram_step1": "1. TelegramでBotを開く",
        "link_telegram_open_bot": "@{bot} を開く",
        "link_telegram_manual": "TelegramでBotを開き、次のメッセージを送ってください：/start link_{code}",
        "link_telegram_step2": "2. コードを確認",
        "link_telegram_step2_body": "リンクにコード入りなので、開始ボタンを押すだけ。",
        "link_telegram_back": "← 設定に戻る",
        "error_404_title": "ページが見つかりません",
        "error_404_body": "リンクが古いか、ページが移動された可能性があります。",
        "error_back_home": "ホームに戻る",
        "app_title": "マイ・ダッシュボード",
        "app_recent": "最近の取引",
        "app_empty_title": "まだ記録がありません。",
        "app_empty_hint": "下に「夕食 2050」と入力して始めましょう。",
        "app_chat_placeholder": "例: 夕食 2050 / +給料 300000",
        "app_chat_send": "送信",
        "app_chat_hint": "+ で収入。通貨（「30 usd」）や日付（「昨日」）も指定できます。",
        "app_delete_confirm": "この記録を削除しますか？",
        "app_low_confidence": "カテゴリが不確かです。修正:",
        "app_backdated": "📅 {date} に記録",
        "recurring_add_title": "新規定期",
        "recurring_add_button": "作成",
        "recurring_list_title": "定期一覧",
        "recurring_empty_state": "定期はまだありません。",
        "recurring_added": "✅ 定期を作成しました。",
        "recurring_toggled": "🔄 ステータスを更新。",
        "recurring_deleted": "🗑️ 定期を削除しました。",
        "recurring_toggle": "停止/再開",
        "recurring_delete": "削除",
        "recurring_delete_confirm": "この定期を削除しますか？",
        "recurring_day_label": "{day}日",
        "page_title_dashboard": "Finance Dashboard",
        "login_title": "💰 Finance Dashboard",
        "login_caption": "Telegramのユーザー名と /setpassword で設定したパスワードでログイン",
        "login_username": "Telegramユーザー名",
        "login_password": "パスワード",
        "login_submit": "ログイン",
        "login_empty": "すべてのフィールドを入力してください。",
        "login_invalid": "ユーザー名またはパスワードが無効です。ボットで /setpassword を使用してください",
        "sidebar_caption": "家計管理パネル",
        "sidebar_logout": "🚪 ログアウト",
        "sidebar_period": "📅 期間",
        "sidebar_quick": "⏱️ クイック選択",
        "quick_today": "今日",
        "quick_week": "今週",
        "quick_month": "今月",
        "quick_last_month": "先月",
        "quick_3months": "3ヶ月",
        "quick_6months": "6ヶ月",
        "quick_year": "1年",
        "quick_custom": "カスタム",
        "sidebar_categories": "🏷️ カテゴリ",
        "sidebar_period_label": "期間",
        "sidebar_records": "件数",
        "sidebar_lang": "🌐 言語",
        "title": "💰 家計ダッシュボード — {period}",
        "no_data": "この期間の記録はありません。Telegramボットで記録してください！",
        "comparison_title": "📊 前期間との比較",
        "prev_period": "前期間: {start} — {end}",
        "current_period_label": "今回",
        "previous_period_label": "前回",
        "delta_expenses": "支出",
        "delta_income": "収入",
        "delta_balance": "残高",
        "delta_tx": "取引",
        "no_prev_data": "比較する前期間のデータがありません。",
        "kpi_total": "支出合計",
        "kpi_income": "収入合計",
        "kpi_balance": "残高",
        "kpi_tx": "取引数",
        "kpi_top": "トップカテゴリ",
        "sidebar_type": "📊 タイプ",
        "type_all": "すべて",
        "type_expense": "支出",
        "type_income": "収入",
        "col_type": "タイプ",
        "chart_timeline": "📈 支出推移",
        "chart_donut": "🍩 カテゴリ分布",
        "chart_bar": "📊 カテゴリ別支出",
        "chart_cumulative": "📉 累計支出",
        "chart_monthly": "📅 月別比較（過去12ヶ月）",
        "chart_no_history": "過去の月別データがありません。",
        "top_expenses": "🔝 高額支出",
        "all_tx": "📋 全取引",
        "search": "🔍 説明で検索",
        "showing": "{total}件中{shown}件を表示",
        "col_id": "ID",
        "col_datetime": "日時",
        "col_desc": "説明",
        "col_value": "金額",
        "col_category": "カテゴリ",
        "currency_axis": "¥",
        "cumulative_axis": "¥（累計）",
        "admin_title": "🛡️ 管理パネル",
        "admin_kpi_users": "ユーザー数",
        "admin_kpi_active7": "アクティブ（7日）",
        "admin_kpi_active30": "アクティブ（30日）",
        "admin_kpi_total_tx": "総取引数",
        "admin_users_table": "👥 ユーザー一覧",
        "admin_col_user": "ユーザー",
        "admin_col_lang": "言語",
        "admin_col_tx": "取引数",
        "admin_col_expenses": "支出",
        "admin_col_income": "収入",
        "admin_col_balance": "残高",
        "admin_col_first": "初回活動",
        "admin_col_last": "最終活動",
        "admin_chart_daily": "📈 日次プラットフォーム活動",
        "admin_chart_users": "👥 日別アクティブユーザー数",
        "admin_no_data": "プラットフォームデータがありません。",
        "admin_switch_personal": "👤 マイダッシュボード",
        "admin_switch_admin": "🛡️ 管理パネル",
        "settings_title": "⚙️ 設定",
        "settings_currency": "💱 デフォルト通貨",
        "settings_timezone": "🕐 タイムゾーン",
        "settings_saved": "✅ 設定を保存しました！",
        "export_csv": "📥 CSVエクスポート",
        "export_pdf": "📥 PDFエクスポート",
        "sidebar_currency_filter": "💱 通貨",
        "currency_all": "すべて",
        "col_currency": "通貨",
        "recurring_title": "🔄 定期取引",
        "recurring_col_desc": "説明",
        "recurring_col_amount": "金額",
        "recurring_col_day": "日",
        "recurring_col_status": "ステータス",
        "recurring_col_next": "次回",
        "recurring_active": "有効",
        "recurring_paused": "一時停止",
    },
}

LANG_LABELS = {"pt": "🇧🇷 Português", "en": "🇺🇸 English", "ja": "🇯🇵 日本語"}

CURRENCY_LABELS = {
    "BRL": "🇧🇷 BRL — Real",
    "USD": "🇺🇸 USD — Dollar",
    "EUR": "🇪🇺 EUR — Euro",
    "JPY": "🇯🇵 JPY — Yen",
    "GBP": "🇬🇧 GBP — Pound",
}

TIMEZONE_LABELS: dict[str, str] = {
    "America/Sao_Paulo": "🇧🇷 São Paulo (GMT-3)",
    "America/New_York": "🇺🇸 New York (GMT-5)",
    "America/Chicago": "🇺🇸 Chicago (GMT-6)",
    "America/Los_Angeles": "🇺🇸 Los Angeles (GMT-8)",
    "Europe/London": "🇬🇧 London (GMT+0)",
    "Europe/Berlin": "🇪🇺 Berlin (GMT+1)",
    "Europe/Lisbon": "🇵🇹 Lisbon (GMT+0)",
    "Asia/Tokyo": "🇯🇵 Tokyo (GMT+9)",
    "Asia/Shanghai": "🇨🇳 Shanghai (GMT+8)",
    "Australia/Sydney": "🇦🇺 Sydney (GMT+11)",
}


# ---------------------------------------------------------------------------
# Lookup helper
# ---------------------------------------------------------------------------


def t(key: str, lang: str = "pt", **kwargs: object) -> str:
    """Look up a bot translation key, falling back to Portuguese."""
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    text = BOT.get(lang, BOT["pt"]).get(key) or BOT["pt"].get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text


def d(key: str, lang: str = "pt", **kwargs: object) -> str:
    """Look up a dashboard translation key, falling back to Portuguese."""
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    text = DASH.get(lang, DASH["pt"]).get(key) or DASH["pt"].get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text
