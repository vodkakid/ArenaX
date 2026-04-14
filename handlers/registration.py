"""
Registro v4: T&C → Tag CR (formato) → Username → Pago móvil → Link amistad
Sin ninguna llamada a API externa. /resetear para testing.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import database as db
import services
from utils import (kb_terms, kb_confirm_tag, kb_banks, kb_main_menu,
                   business_hours_str)
from config import BANKS as BANKS_CONFIG, ADMIN_IDS

logger = logging.getLogger(__name__)

WAITING_TC, WAITING_TAG, CONFIRM_TAG, WAITING_USERNAME, \
    WAITING_PHONE, WAITING_CEDULA, WAITING_BANK, WAITING_FRIEND = range(8)
RESET_CONFIRM = 99


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user   = update.effective_user
    player = db.get_player(user.id)

    if player:
        status = player["status"]
        if status == "banned":
            await update.message.reply_text("⛔ Tu cuenta ha sido suspendida permanentemente.")
            return ConversationHandler.END
        if status == "suspended":
            await update.message.reply_text(
                "🚫 Cuenta suspendida temporalmente. Contacta al administrador.")
            return ConversationHandler.END
        welcome = db.get_text("welcome")
        await update.message.reply_text(
            f"{welcome}\n\n¡Ya estás registrado, *{player['cr_name']}*! 🎮",
            parse_mode="Markdown", reply_markup=kb_main_menu()
        )
        return ConversationHandler.END

    welcome = db.get_text("welcome")
    terms   = db.get_text("terms")
    await update.message.reply_text(welcome, parse_mode="Markdown")
    await update.message.reply_text(
        f"{terms}\n\n¿Aceptas los términos y condiciones?",
        parse_mode="Markdown", reply_markup=kb_terms()
    )
    return WAITING_TC


# ── T&C ───────────────────────────────────────────────────────────────────────

async def accept_tc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_reply_markup(None)
    await update.callback_query.message.reply_text(
        "✅ *Términos aceptados.*\n\n"
        "Ingresa tu *tag de Clash Royale*.\n"
        "Lo encuentras en tu perfil dentro del juego.\n\n"
        "Escríbelo con o sin `#` — Ejemplo: `CRQUJV2RQ`",
        parse_mode="Markdown"
    )
    return WAITING_TAG


async def reject_tc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "❌ No puedes usar ArenaX sin aceptar los términos. Hasta pronto."
    )
    return ConversationHandler.END


# ── Tag CR ────────────────────────────────────────────────────────────────────

async def receive_tag(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    tag = services.normalize_tag(raw)

    if not services.is_valid_tag_format(tag):
        await update.message.reply_text(
            "⚠️ El tag no parece válido.\n\n"
            "Debe tener entre 3 y 12 letras/números (A-Z, 0-9).\n"
            "Ejemplo: `#CRQUJV2RQ`\n\nIntenta de nuevo:",
            parse_mode="Markdown"
        )
        return WAITING_TAG

    existing = db.get_player_by_tag(tag)
    if existing:
        await update.message.reply_text(
            "⚠️ Ese tag ya está registrado. Si es un error contacta al administrador."
        )
        return WAITING_TAG

    ctx.user_data["cr_tag"] = tag
    await update.message.reply_text(
        f"Tag: `{tag}`\n\n¿Es correcto?",
        parse_mode="Markdown",
        reply_markup=kb_confirm_tag()
    )
    return CONFIRM_TAG


async def confirm_tag(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    if update.callback_query.data == "tag_no":
        await update.callback_query.edit_message_text(
            "Ingresa tu tag de Clash Royale:"
        )
        return WAITING_TAG

    await update.callback_query.edit_message_text(
        f"✅ Tag `{ctx.user_data['cr_tag']}` guardado.\n\n"
        "¿Cuál es tu *nombre de jugador* en Clash Royale?\n"
        "_(Como aparece en el juego)_",
        parse_mode="Markdown"
    )
    return WAITING_USERNAME


# ── Username (nombre en CR) ───────────────────────────────────────────────────

async def receive_username(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 1 or len(name) > 30:
        await update.message.reply_text(
            "⚠️ El nombre debe tener entre 1 y 30 caracteres. Intenta de nuevo:"
        )
        return WAITING_USERNAME

    ctx.user_data["cr_name"] = name
    await update.message.reply_text(
        f"👤 Nombre: *{name}*\n\n"
        "📱 Ingresa tu *número de teléfono* para pago móvil:\n"
        "Ejemplo: `0412-1234567`",
        parse_mode="Markdown"
    )
    return WAITING_PHONE


# ── Datos bancarios ───────────────────────────────────────────────────────────

async def receive_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    phone  = update.message.text.strip()
    digits = "".join(filter(str.isdigit, phone))
    if len(digits) < 10:
        await update.message.reply_text(
            "⚠️ Número inválido. Ejemplo: `0412-1234567`",
            parse_mode="Markdown"
        )
        return WAITING_PHONE
    ctx.user_data["phone"] = phone
    await update.message.reply_text(
        "🪪 Ingresa tu *cédula de identidad*\n"
        "Ejemplo: `V-12345678` o solo `12345678`",
        parse_mode="Markdown"
    )
    return WAITING_CEDULA


async def receive_cedula(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().upper()
    if not raw.startswith("V-") and not raw.startswith("E-"):
        digits = "".join(filter(str.isdigit, raw))
        raw    = "V-" + digits
    ctx.user_data["cedula"] = raw
    await update.message.reply_text(
        "🏦 Selecciona tu *banco*:",
        parse_mode="Markdown",
        reply_markup=kb_banks()
    )
    return WAITING_BANK


async def receive_bank(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    code      = update.callback_query.data.replace("bank_", "")
    bank_name = next((name for c, name in BANKS_CONFIG if c == code), "Banco desconocido")
    ctx.user_data["bank_code"] = code
    ctx.user_data["bank_name"] = bank_name
    await update.callback_query.edit_message_text(
        f"✅ Banco: *{bank_name}*\n\n"
        "🔗 Por último, ingresa tu *link de amistad de Clash Royale*\n"
        "_(Perfil → ··· → Compartir → Copiar link)_",
        parse_mode="Markdown"
    )
    return WAITING_FRIEND


async def receive_friend_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    link_lower = link.lower()
    valid = (
        "clashroyale" in link_lower
        or "supercell" in link_lower
        or link.startswith("https://")
        or link.startswith("http://")
    )
    if not valid:
        await update.message.reply_text(
            "⚠️ El link no parece válido.\n"
            "Ejemplo: `https://link.clashroyale.com/invite/friend/...`\n\n"
            "Cópialo desde tu perfil en el juego:",
            parse_mode="Markdown"
        )
        return WAITING_FRIEND

    user = update.effective_user
    ud   = ctx.user_data

    try:
        db.create_player(
            telegram_id = user.id,
            username    = user.username or "",
            cr_tag      = ud["cr_tag"],
            cr_name     = ud["cr_name"],
            friend_link = link,
            phone       = ud["phone"],
            cedula      = ud["cedula"],
            bank_code   = ud["bank_code"],
            bank_name   = ud["bank_name"],
        )
    except Exception as e:
        logger.error(f"Error registrando jugador {user.id}: {e}")
        await update.message.reply_text(
            "❌ Error al guardar tu registro. Intenta de nuevo con /start"
        )
        return ConversationHandler.END

    cr_name = ud["cr_name"]
    ctx.user_data.clear()
    await update.message.reply_text(
        f"🎉 *¡Bienvenido a ArenaX, {cr_name}!*\n\n"
        f"Tu cuenta está lista. ¡A competir y ganar!\n\n"
        f"⏰ Horario: {business_hours_str()}",
        parse_mode="Markdown",
        reply_markup=kb_main_menu()
    )
    return ConversationHandler.END


# ── /resetear ────────────────────────────────────────────────────────────────

async def cmd_resetear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user   = update.effective_user
    is_adm = user.id in ADMIN_IDS
    if is_adm:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 Borrar mi cuenta",       callback_data="reset_me")],
            [InlineKeyboardButton("💥 Borrar TODA la base de datos", callback_data="reset_all")],
            [InlineKeyboardButton("❌ Cancelar",               callback_data="reset_cancel")],
        ])
        await update.message.reply_text(
            "⚠️ *¿Qué deseas resetear?*\n\n"
            "• *Mi cuenta* — solo tu registro\n"
            "• *TODA la BD* — jugadores, partidas, pagos, cola\n"
            "_(textos y config se mantienen)_\n\n"
            "Acción *irreversible*.",
            parse_mode="Markdown", reply_markup=kb
        )
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Sí, borrar mi cuenta", callback_data="reset_me")],
            [InlineKeyboardButton("❌ Cancelar",              callback_data="reset_cancel")],
        ])
        await update.message.reply_text(
            "⚠️ ¿Seguro que quieres borrar tu cuenta?\n"
            "Se eliminarán todos tus datos. Podrás registrarte de nuevo con /start.",
            reply_markup=kb
        )
    return RESET_CONFIRM


async def handle_reset_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    choice = update.callback_query.data
    user   = update.effective_user

    if choice == "reset_cancel":
        await update.callback_query.edit_message_text("❌ Reset cancelado.")
        return ConversationHandler.END

    if choice == "reset_me":
        _reset_player(user.id)
        ctx.user_data.clear()
        await update.callback_query.edit_message_text(
            "✅ *Tu cuenta fue borrada.*\nUsa /start para registrarte de nuevo.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    if choice == "reset_all" and user.id in ADMIN_IDS:
        _reset_all_data()
        ctx.user_data.clear()
        await update.callback_query.edit_message_text(
            "💥 *Base de datos reseteada.*\n"
            "Jugadores, partidas, pagos y cola eliminados.\n"
            "Usa /start para registrarte de nuevo.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    await update.callback_query.edit_message_text("❌ Acción no permitida.")
    return ConversationHandler.END


def _reset_player(telegram_id: int):
    import sqlite3
    from database import _DB_PATH
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("PRAGMA foreign_keys=OFF")
    for table in ["queue", "payments", "withdrawals", "transactions"]:
        conn.execute(f"DELETE FROM {table} WHERE telegram_id=?", (telegram_id,))
    conn.execute(
        "DELETE FROM matches WHERE player1_id=? OR player2_id=?",
        (telegram_id, telegram_id)
    )
    conn.execute("DELETE FROM players WHERE telegram_id=?", (telegram_id,))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()
    conn.close()


def _reset_all_data():
    import sqlite3
    from database import _DB_PATH
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("PRAGMA foreign_keys=OFF")
    for table in ["queue", "payments", "withdrawals", "transactions",
                  "disputes", "matches", "players"]:
        conn.execute(f"DELETE FROM {table}")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()
    conn.close()
