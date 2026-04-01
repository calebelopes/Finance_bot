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
from utils.export import generate_csv, generate_pdf  # noqa: E402
from utils.i18n import (  # noqa: E402
    ALL_GREETINGS,
    CURRENCY_LABELS,
    LANG_LABELS,
    MONTHS,
    SUPPORTED_LANGS,
    TIMEZONE_LABELS,
    cat_name,
    detect_lang,
    fmt_currency,
    t,
)
from utils.parser import parse_number_ptbr, parse_smart  # noqa: E402

log = logging.getLogger(__name__)


def _dashboard_url() -> str:
    return os.getenv("DASHBOARD_URL", "http://localhost:8501")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_timezone(user_id: int | None = None) -> ZoneInfo:
    """Return the user's timezone if available, else fall back to env var / default."""
    if user_id:
        prefs = db.get_user_preferences(user_id)
        tz_name = prefs.get("timezone")
        if tz_name:
            try:
                return ZoneInfo(tz_name)
            except (KeyError, Exception):
                pass
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


def _period_range_utc(period: str, user_id: int | None = None) -> tuple[str, str]:
    tz = _get_timezone(user_id)
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


def _utc_to_local_str(utc_iso: str, user_id: int | None = None) -> str:
    tz = _get_timezone(user_id)
    dt = datetime.datetime.fromisoformat(utc_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    return dt.astimezone(tz).strftime("%H:%M")


def _format_transactions(transactions: list[dict], title: str, lang: str, user_id: int | None = None) -> str:
    if not transactions:
        return f"{title}\n\n{t('no_expenses', lang)}"

    lines = [title, ""]
    total_expense = 0.0
    total_income = 0.0
    for tx in transactions:
        tx_type = tx.get("type", "expense")
        is_income = tx_type == "income"
        icon = "🟢" if is_income else "🔴"
        if is_income:
            total_income += tx["amount_original"]
        else:
            total_expense += tx["amount_original"]
        cur = tx.get("currency_code", "BRL")
        value_str = fmt_currency(tx["amount_original"], lang, currency_code=cur)
        time_str = _utc_to_local_str(tx["created_at"], user_id)
        cat_display = cat_name(tx["category"], lang)
        sign = "+" if is_income else "-"
        line = f"  {icon} #{tx['id']}  [{time_str}]  {tx['description']}: {sign}{value_str}  [{cat_display}]"
        if tx.get("amount_converted") and tx.get("exchange_rate"):
            user_cur = db.get_user_preferences(user_id).get("currency_default", "BRL") if user_id else "BRL"
            converted_str = fmt_currency(tx["amount_converted"], lang, currency_code=user_cur)
            line += f"  ≈ {converted_str}"
        lines.append(line)

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
        start_utc, end_utc = _period_range_utc("today", user.id)
        txs = db.get_transactions(user.id, start_utc, end_utc)
        now_local = datetime.datetime.now(_get_timezone(user.id))
        title = t("today_title", lang, date=now_local.strftime("%d/%m/%Y"))
        await update.message.reply_text(_format_transactions(txs, title, lang, user.id))
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
        start_utc, end_utc = _period_range_utc("week", user.id)
        txs = db.get_transactions(user.id, start_utc, end_utc)
        title = t("week_title", lang)
        await update.message.reply_text(_format_transactions(txs, title, lang, user.id))
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
        start_utc, end_utc = _period_range_utc("month", user.id)
        txs = db.get_transactions(user.id, start_utc, end_utc)
        now_local = datetime.datetime.now(_get_timezone(user.id))
        month_name = MONTHS[lang][now_local.month]
        title = t("month_title", lang, month=month_name, year=now_local.year)
        await update.message.reply_text(_format_transactions(txs, title, lang, user.id))
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
        start_utc, end_utc = _period_range_utc("month", user.id)
        now_local = datetime.datetime.now(_get_timezone(user.id))
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
            tx_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text(t("delete_usage", lang))
            return

        if db.delete_transaction(user.id, tx_id):
            await update.message.reply_text(t("deleted", lang, id=tx_id))
        else:
            await update.message.reply_text(t("delete_not_found", lang, id=tx_id))
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


async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    prefs = db.get_user_preferences(user.id)
    lines = [
        t("config_title", lang),
        t("config_lang", lang, value=LANG_LABELS.get(lang, lang)),
        t("config_currency", lang, value=prefs.get("currency_default", "BRL")),
        t("config_timezone", lang, value=prefs.get("timezone", "America/Sao_Paulo")),
        "",
        t("config_hint", lang),
    ]
    await update.message.reply_text("\n".join(lines))


async def cmd_setcurrency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"currency:{code}")]
        for code, label in CURRENCY_LABELS.items()
    ]
    await update.message.reply_text(
        t("setcurrency_prompt", lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cb_setcurrency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chosen = query.data.split(":", 1)[1].upper()
    if not db.is_valid_currency(chosen):
        return
    user_id = query.from_user.id
    db.set_user_preference(user_id, "currency_default", chosen)
    lang = db.get_user_lang(user_id)
    await query.edit_message_text(t("setcurrency_done", lang, currency=chosen))


async def cmd_settimezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"tz:{tz_key}")]
        for tz_key, label in TIMEZONE_LABELS.items()
    ]
    await update.message.reply_text(
        t("settimezone_prompt", lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cb_settimezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chosen = query.data.split(":", 1)[1]
    if chosen not in TIMEZONE_LABELS:
        return
    user_id = query.from_user.id
    db.set_user_preference(user_id, "timezone", chosen)
    lang = db.get_user_lang(user_id)
    await query.edit_message_text(t("settimezone_done", lang, timezone=chosen))


async def cmd_recurring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    try:
        rules = db.get_recurring(user.id)
        if not rules:
            await update.message.reply_text(t("recurring_empty", lang))
            return
        lines = [t("recurring_title", lang), ""]
        for r in rules:
            icon = "🟢" if r["type"] == "income" else "🔴"
            status = t("recurring_active", lang) if r["active"] else t("recurring_paused", lang)
            cat_display = cat_name(r["category"] or "Outros", lang)
            amount_str = fmt_currency(r["amount"], lang, currency_code=r.get("currency_code"))
            lines.append(t("recurring_item", lang,
                           id=r["id"], icon=icon, description=r["description"],
                           amount=amount_str, category=cat_display,
                           day=r["day_of_month"], status=status))
        await update.message.reply_text("\n".join(lines))
    except Exception:
        log.exception("Error in /recurring")
        await update.message.reply_text(t("error", lang))


async def cmd_addrecurring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    try:
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(t("addrecurring_usage", lang))
            return
        raw_desc = context.args[0]
        is_income = raw_desc.startswith("+")
        desc = raw_desc.lstrip("+") if is_income else raw_desc
        action_type = "income" if is_income else "expense"

        try:
            amount = parse_number_ptbr(context.args[1])
        except ValueError:
            await update.message.reply_text(t("addrecurring_usage", lang))
            return

        day = None
        if len(context.args) >= 3:
            try:
                day = int(context.args[2])
                day = max(1, min(28, day))
            except ValueError:
                pass

        prefs = db.get_user_preferences(user.id)
        currency = prefs.get("currency_default", "BRL")
        category = categories.infer_category(desc, action_type)
        rec_id = db.add_recurring(
            user.id, desc, amount, category, action_type,
            currency_code=currency, day_of_month=day,
        )
        amount_str = fmt_currency(amount, lang, currency_code=currency)
        rule = db.get_recurring(user.id)
        actual_day = next((r["day_of_month"] for r in rule if r["id"] == rec_id), day)
        await update.message.reply_text(
            t("addrecurring_done", lang, id=rec_id, description=desc, amount=amount_str, day=actual_day)
        )
    except Exception:
        log.exception("Error in /addrecurring")
        await update.message.reply_text(t("error", lang))


async def cmd_delrecurring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    try:
        if not context.args or len(context.args) != 1:
            await update.message.reply_text(t("delrecurring_usage", lang))
            return
        try:
            rec_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text(t("delrecurring_usage", lang))
            return
        if db.delete_recurring(user.id, rec_id):
            await update.message.reply_text(t("delrecurring_done", lang, id=rec_id))
        else:
            await update.message.reply_text(t("delrecurring_not_found", lang, id=rec_id))
    except Exception:
        log.exception("Error in /delrecurring")
        await update.message.reply_text(t("error", lang))


async def cmd_togglerecurring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    try:
        if not context.args or len(context.args) != 1:
            await update.message.reply_text(t("togglerecurring_usage", lang))
            return
        try:
            rec_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text(t("togglerecurring_usage", lang))
            return
        result = db.toggle_recurring(user.id, rec_id)
        if result is None:
            await update.message.reply_text(t("delrecurring_not_found", lang, id=rec_id))
        else:
            status = t("recurring_active", lang) if result else t("recurring_paused", lang)
            await update.message.reply_text(t("togglerecurring_done", lang, id=rec_id, status=status))
    except Exception:
        log.exception("Error in /togglerecurring")
        await update.message.reply_text(t("error", lang))


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_authorized(user.id):
        await update.message.reply_text(t("unauthorized", "pt"))
        return
    lang = _get_lang(update)
    try:
        period = "month"
        if context.args:
            p = context.args[0].lower()
            if p in ("today", "hoje", "kyou"):
                period = "today"
            elif p in ("week", "semana", "shuu"):
                period = "week"
            elif p in ("month", "mes", "tsuki"):
                period = "month"

        start_utc, end_utc = _period_range_utc(period, user.id)
        txs = db.get_transactions(user.id, start_utc, end_utc)
        if not txs:
            await update.message.reply_text(t("export_empty", lang))
            return

        csv_bytes = generate_csv(txs, lang)
        pdf_bytes = generate_pdf(txs, lang, period)

        period_label = {"today": "today", "week": "week", "month": "month"}[period]
        await update.message.reply_document(
            document=csv_bytes,
            filename=f"finance_{period_label}.csv",
            caption=t("export_csv_caption", lang, period=period_label),
        )
        await update.message.reply_document(
            document=pdf_bytes,
            filename=f"finance_{period_label}.pdf",
            caption=t("export_pdf_caption", lang, period=period_label),
        )
    except Exception:
        log.exception("Error in /export")
        await update.message.reply_text(t("error", lang))


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
            tx_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text(t("edit_usage", lang))
            return
        try:
            new_value = parse_number_ptbr(context.args[1])
        except ValueError:
            await update.message.reply_text(t("edit_usage", lang))
            return

        if db.edit_transaction(user.id, tx_id, new_value):
            await update.message.reply_text(
                t("edited", lang, id=tx_id, value=fmt_currency(new_value, lang))
            )
        else:
            await update.message.reply_text(t("edit_not_found", lang, id=tx_id))
    except Exception:
        log.exception("Error in /edit")
        await update.message.reply_text(t("error", lang))


# ---------------------------------------------------------------------------
# Free-text message handler
# ---------------------------------------------------------------------------


_LOW_CONFIDENCE_THRESHOLD = 0.85


def _compute_backdated_ts(date_offset: int, user_id: int) -> str:
    """Return an ISO UTC timestamp backdated by *date_offset* days."""
    tz = _get_timezone(user_id)
    now = datetime.datetime.now(tz)
    target = (now + datetime.timedelta(days=date_offset)).replace(
        hour=12, minute=0, second=0, microsecond=0,
    )
    return target.astimezone(datetime.UTC).replace(microsecond=0).isoformat()


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
        result = parse_smart(parse_text)
    except ValueError:
        await update.message.reply_text(t("invalid", lang))
        return

    try:
        description = result.description
        value = result.value
        parsed_currency = result.currency
        date_offset = result.date_offset

        category, confidence = categories.infer_category_with_confidence(
            result.raw_description or description, action_type,
        )

        prefs = db.get_user_preferences(user.id)
        user_currency = prefs.get("currency_default", "BRL")
        tx_currency = parsed_currency or user_currency

        amount_converted = None
        exchange_rate = None
        if tx_currency != user_currency:
            amount_converted, exchange_rate = db.convert_amount(value, tx_currency, user_currency)

        created_at_override = None
        if date_offset is not None and date_offset != 0:
            created_at_override = _compute_backdated_ts(date_offset, user.id)

        tx_id = db.store_transaction(
            user.id, user.username, description, value, category, action_type,
            currency_code=tx_currency,
            amount_converted=amount_converted,
            exchange_rate=exchange_rate,
            created_at_override=created_at_override,
            confidence_score=confidence,
        )

        value_str = fmt_currency(value, lang, currency_code=tx_currency)
        cat_display = cat_name(category, lang)
        msg_key = "stored_income" if is_income else "stored_expense"
        reply = t(msg_key, lang, id=tx_id, description=description, value=value_str, category=cat_display)

        if amount_converted and exchange_rate:
            converted_str = fmt_currency(amount_converted, lang, currency_code=user_currency)
            reply += f"\n  ≈ {converted_str} (1 {tx_currency} = {exchange_rate:.4f} {user_currency})"

        if created_at_override and date_offset is not None:
            tz = _get_timezone(user.id)
            bd_dt = datetime.datetime.fromisoformat(created_at_override).astimezone(tz)
            reply += "\n" + t("backdated", lang, date=bd_dt.strftime("%d/%m/%Y"))

        # Low confidence: offer category correction via inline keyboard
        markup = None
        if 0 < confidence < _LOW_CONFIDENCE_THRESHOLD:
            top_cats = categories.get_top_categories(
                result.raw_description or description, action_type, n=4,
            )
            buttons = []
            for cat, _score in top_cats:
                if cat != category:
                    display = cat_name(cat, lang)
                    buttons.append(
                        InlineKeyboardButton(display, callback_data=f"fixcat:{tx_id}:{cat}")
                    )
            if buttons:
                reply += "\n" + t("low_confidence", lang, category=cat_display)
                markup = InlineKeyboardMarkup([buttons[:4]])

        await update.message.reply_text(reply, reply_markup=markup)
        log.info(
            "Stored #%d [%s] for %s (%d): %s = %.2f %s [%s] (conf=%.2f)",
            tx_id, action_type, user.username, user.id,
            description, value, tx_currency, category, confidence,
        )
    except Exception:
        log.exception("Error storing transaction for user %d", user.id)
        await update.message.reply_text(t("error", lang))


async def cb_fixcat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline category-correction button presses."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":", 2)
    if len(parts) != 3:
        return
    try:
        tx_id = int(parts[1])
    except ValueError:
        return
    new_category = parts[2]
    user_id = query.from_user.id
    lang = db.get_user_lang(user_id)

    if db.update_transaction_category(user_id, tx_id, new_category):
        cat_display = cat_name(new_category, lang)
        await query.edit_message_text(
            query.message.text + "\n" + t("category_corrected", lang, id=tx_id, category=cat_display)
        )
    log.info("User %d corrected tx #%d category to %s", user_id, tx_id, new_category)


# ---------------------------------------------------------------------------
# Application bootstrap
# ---------------------------------------------------------------------------


async def _process_due_recurring(application: Application) -> None:
    """Execute all overdue recurring transactions and notify users."""
    due = db.get_due_recurring()
    for rule in due:
        try:
            cat = rule.get("category") or "Outros"
            tx_id = db.store_transaction(
                rule["user_id"], None, rule["description"], rule["amount"],
                cat, rule["type"],
                currency_code=rule.get("currency_code", "BRL"),
                source="recurring",
                recurring_id=rule["id"],
            )
            db.log_recurring_execution(rule["id"], tx_id)
            db.advance_recurring(rule["id"])
            lang = db.get_user_lang(rule["user_id"])
            amount_str = fmt_currency(rule["amount"], lang, currency_code=rule.get("currency_code"))
            try:
                await application.bot.send_message(
                    rule["user_id"],
                    t("recurring_executed", lang, tx_id=tx_id,
                      description=rule["description"], amount=amount_str),
                )
            except Exception:
                log.warning("Could not notify user %d about recurring #%d", rule["user_id"], rule["id"])
            log.info("Executed recurring #%d → tx #%d for user %d", rule["id"], tx_id, rule["user_id"])
        except Exception:
            log.exception("Error executing recurring rule #%d", rule["id"])


async def _recurring_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic job that runs once per day to process due recurring transactions."""
    await _process_due_recurring(context.application)


async def _post_init(application: Application) -> None:
    db.log_app_event("app_started")
    log.info("Bot started successfully")
    await _process_due_recurring(application)


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

    # Multilingual command aliases (pt / en / ja)
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler(["help", "ajuda", "tasukete"], cmd_help))
    application.add_handler(CommandHandler(["lang", "idioma", "gengo"], cmd_lang))
    application.add_handler(CallbackQueryHandler(cb_lang, pattern=r"^lang:"))
    application.add_handler(CommandHandler(["today", "hoje", "kyou"], cmd_today))
    application.add_handler(CommandHandler(["week", "semana", "shuu"], cmd_week))
    application.add_handler(CommandHandler(["month", "mes", "tsuki"], cmd_month))
    application.add_handler(CommandHandler(["summary", "resumo", "matome"], cmd_summary))
    application.add_handler(CommandHandler(["delete", "excluir", "sakujo"], cmd_delete))
    application.add_handler(CommandHandler(["edit", "editar", "henshuu"], cmd_edit))
    application.add_handler(CommandHandler(["setpassword", "senha", "password"], cmd_setpassword))
    application.add_handler(CommandHandler(["admin", "kanri"], cmd_admin))
    application.add_handler(CommandHandler(["config", "configurar", "settei"], cmd_config))
    application.add_handler(CommandHandler(["setcurrency", "moeda", "tsuuka"], cmd_setcurrency))
    application.add_handler(CallbackQueryHandler(cb_setcurrency, pattern=r"^currency:"))
    application.add_handler(CommandHandler(["settimezone", "fuso", "jikan"], cmd_settimezone))
    application.add_handler(CallbackQueryHandler(cb_settimezone, pattern=r"^tz:"))
    application.add_handler(CommandHandler(["recurring", "recorrente", "teiki"], cmd_recurring))
    application.add_handler(CommandHandler(["addrecurring", "novarecorrente", "teikitsuika"], cmd_addrecurring))
    application.add_handler(CommandHandler(["delrecurring", "excluirrecorrente", "teikisakujo"], cmd_delrecurring))
    application.add_handler(CommandHandler(["togglerecurring", "alternarrecorrente", "teikikiri"], cmd_togglerecurring))
    application.add_handler(CommandHandler(["export", "exportar", "shukuryoku"], cmd_export))
    application.add_handler(CallbackQueryHandler(cb_fixcat, pattern=r"^fixcat:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(_recurring_job, interval=86400, first=60)

    application.run_polling()


if __name__ == "__main__":
    main()
