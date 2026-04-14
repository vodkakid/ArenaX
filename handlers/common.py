"""
Handlers comunes: /menu, /cancel, botón de volver al menú.
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import database as db
from utils import kb_main_menu, kb_admin_main, is_business_hours, business_hours_str
from config import ADMIN_IDS


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user   = update.effective_user
    player = db.get_player(user.id)

    if not player:
        await update.message.reply_text("⚠️ No tienes cuenta. Usa /start para registrarte.")
        return

    if player["status"] in ("banned", "suspended"):
        await update.message.reply_text("⛔ Tu cuenta está restringida.")
        return

    if not is_business_hours():
        from utils import fmt_usd
        await update.message.reply_text(
            f"🕙 ArenaX opera de *10:00 am a 10:00 pm* (hora Venezuela).\n"
            f"Fuera de horario solo puedes consultar tu perfil y balance.",
            parse_mode="Markdown",
            reply_markup=kb_main_menu()
        )
        return

    await update.message.reply_text(
        f"🏠 *Menú principal*\n\nBienvenido, *{player['cr_name']}* 👋",
        parse_mode="Markdown",
        reply_markup=kb_main_menu()
    )


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "❌ Operación cancelada.",
        reply_markup=kb_main_menu()
    )
    return ConversationHandler.END


async def back_to_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    ctx.user_data.clear()
    user   = update.effective_user
    player = db.get_player(user.id)
    name   = player["cr_name"] if player else user.first_name

    await update.callback_query.edit_message_text(
        f"🏠 *Menú principal*\n\nBienvenido, *{name}* 👋",
        parse_mode="Markdown",
        reply_markup=kb_main_menu()
    )
