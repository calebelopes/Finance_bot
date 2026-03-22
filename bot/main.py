import datetime
import logging
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update  # noqa: E402
from telegram.ext import (  # noqa: E402
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest  # noqa: E402

from utils import categories, db  # noqa: E402
from utils.i18n import (  # noqa: E402
    ALL_GREETINGS,
    LANG_LABELS,
    MONTHS,
    SUPPORTED_LANGS,
    cat_name,
    detect_lang,
    fmt_currency,
    t,
)
from utils.parser import parse_action_value, parse_number_ptbr  # noqa: E402

log = logging.getLogger(__name__)


def _dashboard_url() -> str:
    return os.getenv("DASHBOARD_URL", "http://localhost:8501")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_timezone() -> ZoneInfo:
    return ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo"))


def _is_authorized(user_id: int) -> bool:
    allowed = os.getenv("ALLOWED_USERS", "").strip()
    if not allowed:
        return True
    allowed_ids = set()
    for uid in allowed.split(","):
        uid = uid.strip()
        if uid.isdigit():
            allowed_ids.add(int(uid))
    return user_id in allowed_ids


def _get_lang(update: Update) -> str:
    """Get user's language, auto-detecting and persisting on first contact."""
    user = update.effective_user
    lang = db.get_user_lang(user.id)
    if lang and lang != "pt":
        return lang
    detected = detect_lang(user.language_code)
    db.ensure_user_with_lang(user.id, user.username, detected)
    return detected


def _period_range_utc(period: str) -> tuple[str, str]:
    tz = _get_timezone()
    now_local = datetime.datetime.now(tz)
    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == "today":
        start = today_start
        end = start + datetime.timedelta(days=1)
    elif period == "week":
        start = today_start - datetime.timedelta(days=today_start.weekday())
        end = start + datetime.timedelta(days=7)
    elif period == "month":
        start = today_start.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
    else:
        raise ValueError(f"Unknown period: {period}")

    def to_utc(dt: datetime.datetime) -> str:
        return dt.astimezone(datetime.UTC).replace(microsecond=0).isoformat()

    return to_utc(start), to_utc(end)


def _utc_to_local_str(utc_iso: str) -> str:
    tz = _get_timezone()
    dt = datetime.datetime.fromisoformat(utc_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    return dt.astimezone(tz).strftime("%H:%M")


def _format_actions_list(actions: list[dict], title: str, lang: str) -> str:
    if not actions:
        return f"{title}\n\n{t('no_expenses', lang)}"

    lines = [title, ""]
    total_expense = 0.0
    total_income = 0.0
    for a in actions:
        action_type = a.get("type", "expense")
        is_income = action_type == "income"
        icon = "🟢" if is_income else "🔴"
        if is_income:
            total_income += a["value"]
        else:
            total_expense += a["value"]
        value_str = fmt_currency(a["value"], lang)
        time_str = _utc_to_local_str(a["created_at"])
        cat_display = cat_name(a["category"], lang)
        sign = "+" if is_income else "-"
        lines.append(
            f"  {icon} #{a['id']}  [{time_str}]  {a['action']}: {sign}{value_str}  [{cat_display}]"
        )

    lines.append("")
    if total_income > 0 and total_expense > 0:
        lines.append(f"📈 {t('total_income', lang)}: +{fmt_currency(total_income, lang)}")
        lines.append(f"📉 {t('total_expenses', lang)}: -{fmt_currency(total_expense, lang)}")
        balance = total_income - total_expense
        sign = "+" if balance >= 0 else "-"
        lines.append(f"💰 {t('balance', lang)}: {sign}{fmt_currency(abs(balance), lang)}")
    elif total_income > 0:
        lines.append(f"💰 Total: +{fmt_currency(total_income, lang)}")
    else:
        lines.append(f"Total: -{fmt_currency(total_expense, lang)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    await update.message.reply_text(t("start", lang))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    await update.message.reply_text(t("help", lang, dashboard_url=_dashboard_url()))


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"lang:{code}")]
        for code, label in LANG_LABELS.items()
    ]
    await update.message.reply_text(
        t("lang_prompt", lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cb_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chosen = query.data.split(":", 1)[1]
    if chosen not in SUPPORTED_LANGS:
        return
    db.set_lang(query.from_user.id, chosen)
    await query.edit_message_text(t("lang_set", chosen))


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    try:
        start_utc, end_utc = _period_range_utc("today")
        actions = db.get_actions(user.id, start_utc, end_utc)
        now_local = datetime.datetime.now(_get_timezone())
        title = t("today_title", lang, date=now_local.strftime("%d/%m/%Y"))
        await update.message.reply_text(_format_actions_list(actions, title, lang))
    except Exception:
        log.exception("Error in /today")
        await update.message.reply_text(t("error", lang))


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    try:
        start_utc, end_utc = _period_range_utc("week")
        actions = db.get_actions(user.id, start_utc, end_utc)
        title = t("week_title", lang)
        await update.message.reply_text(_format_actions_list(actions, title, lang))
    except Exception:
        log.exception("Error in /week")
        await update.message.reply_text(t("error", lang))


async def cmd_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    try:
        start_utc, end_utc = _period_range_utc("month")
        actions = db.get_actions(user.id, start_utc, end_utc)
        now_local = datetime.datetime.now(_get_timezone())
        month_name = MONTHS[lang][now_local.month]
        title = t("month_title", lang, month=month_name, year=now_local.year)
        await update.message.reply_text(_format_actions_list(actions, title, lang))
    except Exception:
        log.exception("Error in /month")
        await update.message.reply_text(t("error", lang))


async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    try:
        start_utc, end_utc = _period_range_utc("month")
        now_local = datetime.datetime.now(_get_timezone())
        month_name = MONTHS[lang][now_local.month]
        title = t("summary_title", lang, month=month_name, year=now_local.year)

        expense_rows = db.get_summary_by_category(user.id, start_utc, end_utc, "expense")
        income_rows = db.get_summary_by_category(user.id, start_utc, end_utc, "income")

        if not expense_rows and not income_rows:
            await update.message.reply_text(f"{title}\n\n{t('no_expenses', lang)}")
            return

        lines = [title]
        total_expense = 0.0
        total_income = 0.0

        if expense_rows:
            lines.append(f"\n🔴 {t('total_expenses', lang)}:")
            for r in expense_rows:
                total_expense += r["total"]
                cat_display = cat_name(r["category"], lang)
                lines.append(f"  {cat_display}: {fmt_currency(r['total'], lang)}  ({r['count']}x)")

        if income_rows:
            lines.append(f"\n🟢 {t('total_income', lang)}:")
            for r in income_rows:
                total_income += r["total"]
                cat_display = cat_name(r["category"], lang)
                lines.append(f"  {cat_display}: {fmt_currency(r['total'], lang)}  ({r['count']}x)")

        lines.append("")
        if total_expense > 0:
            lines.append(f"📉 {t('total_expenses', lang)}: {fmt_currency(total_expense, lang)}")
        if total_income > 0:
            lines.append(f"📈 {t('total_income', lang)}: {fmt_currency(total_income, lang)}")
        balance = total_income - total_expense
        sign = "+" if balance >= 0 else "-"
        lines.append(f"💰 {t('balance', lang)}: {sign}{fmt_currency(abs(balance), lang)}")
        await update.message.reply_text("\n".join(lines))
    except Exception:
        log.exception("Error in /summary")
        await update.message.reply_text(t("error", lang))


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    try:
        if not context.args or len(context.args) != 1:
            await update.message.reply_text(t("delete_usage", lang))
            return
        try:
            action_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text(t("delete_usage", lang))
            return

        if db.delete_action(user.id, action_id):
            await update.message.reply_text(t("deleted", lang, id=action_id))
        else:
            await update.message.reply_text(t("delete_not_found", lang, id=action_id))
    except Exception:
        log.exception("Error in /delete")
        await update.message.reply_text(t("error", lang))


async def cmd_setpassword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    try:
        if not context.args:
            await update.message.reply_text(t("password_usage", lang))
            return
        password = " ".join(context.args)
        if len(password) < 4:
            await update.message.reply_text(t("password_too_short", lang))
            return

        db.set_password(user.id, password)

        try:
            await update.message.delete()
        except Exception:
            pass

        await update.effective_chat.send_message(
            t("password_set", lang, dashboard_url=_dashboard_url())
        )
        log.info("Password set for user %s (%d)", user.username, user.id)
    except Exception:
        log.exception("Error in /setpassword")
        await update.message.reply_text(t("error", lang))


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle admin status. Only BOT_OWNER can run this."""
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)

    owner_raw = os.getenv("BOT_OWNER", "").strip()
    if not owner_raw.isdigit() or user.id != int(owner_raw):
        await update.message.reply_text(t("admin_not_allowed", lang))
        return

    target_id = user.id
    if context.args and context.args[0].isdigit():
        target_id = int(context.args[0])

    currently_admin = db.is_admin(target_id)
    db.set_admin(target_id, not currently_admin)
    msg_key = "admin_revoked" if currently_admin else "admin_granted"
    await update.message.reply_text(t(msg_key, lang))


async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    try:
        if not context.args or len(context.args) != 2:
            await update.message.reply_text(t("edit_usage", lang))
            return
        try:
            action_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text(t("edit_usage", lang))
            return
        try:
            new_value = parse_number_ptbr(context.args[1])
        except ValueError:
            await update.message.reply_text(t("edit_usage", lang))
            return

        if db.edit_action_value(user.id, action_id, new_value):
            await update.message.reply_text(
                t("edited", lang, id=action_id, value=fmt_currency(new_value, lang))
            )
        else:
            await update.message.reply_text(t("edit_not_found", lang, id=action_id))
    except Exception:
        log.exception("Error in /edit")
        await update.message.reply_text(t("error", lang))


# ---------------------------------------------------------------------------
# Free-text message handler
# ---------------------------------------------------------------------------


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return

    text = update.message.text if update.message else None
    if not text:
        return

    lang = _get_lang(update)

    normalized = " ".join(text.strip().lower().split())
    if normalized in ALL_GREETINGS:
        await update.message.reply_text(t("greeting", lang))
        return

    is_income = text.strip().startswith("+")
    parse_text = text.strip().lstrip("+").strip() if is_income else text
    action_type = "income" if is_income else "expense"

    try:
        action, value = parse_action_value(parse_text)
    except ValueError:
        await update.message.reply_text(t("invalid", lang))
        return

    try:
        category = categories.infer_category(action, action_type)
        action_id = db.store_action(user.id, user.username, action, value, category, action_type)
        value_str = fmt_currency(value, lang)
        cat_display = cat_name(category, lang)
        msg_key = "stored_income" if is_income else "stored_expense"
        await update.message.reply_text(
            t(msg_key, lang, id=action_id, action=action, value=value_str, category=cat_display)
        )
        log.info(
            "Stored #%d [%s] for %s (%d): %s = %.2f [%s]",
            action_id, action_type, user.username, user.id, action, value, category,
        )
    except Exception:
        log.exception("Error storing action for user %d", user.id)
        await update.message.reply_text(t("error", lang))


# ---------------------------------------------------------------------------
# Application bootstrap
# ---------------------------------------------------------------------------


async def _post_init(_: Application) -> None:
    db.log_app_event("app_started")
    log.info("Bot started successfully")


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )

    db.setup_database()

    token = os.getenv("TOKEN")
    if not token:
        raise RuntimeError("Missing TOKEN environment variable (Telegram bot token).")

    if os.getenv("USE_SYSTEM_CA") == "1":
        try:
            import truststore  # type: ignore[import-untyped]

            truststore.inject_into_ssl()
        except Exception as exc:
            raise RuntimeError(f"Failed to enable system CA store: {exc}") from exc

    ca_bundle = os.getenv("TELEGRAM_CA_BUNDLE")
    request = HTTPXRequest(httpx_kwargs={"verify": ca_bundle}) if ca_bundle else HTTPXRequest()

    application = (
        Application.builder()
        .token(token)
        .request(request)
        .post_init(_post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("lang", cmd_lang))
    application.add_handler(CallbackQueryHandler(cb_lang, pattern=r"^lang:"))
    application.add_handler(CommandHandler("today", cmd_today))
    application.add_handler(CommandHandler("week", cmd_week))
    application.add_handler(CommandHandler("month", cmd_month))
    application.add_handler(CommandHandler("summary", cmd_summary))
    application.add_handler(CommandHandler("delete", cmd_delete))
    application.add_handler(CommandHandler("edit", cmd_edit))
    application.add_handler(CommandHandler("setpassword", cmd_setpassword))
    application.add_handler(CommandHandler("admin", cmd_admin))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()


if __name__ == "__main__":
    main()
