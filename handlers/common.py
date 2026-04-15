"""
Handlers comunes: /menu, /cancel, volver al menú.
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import database as db
from utils import kb_main_menu, is_business_hours
from config import ADMIN_IDS


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user   = update.effective_user
    player = db.get_player(user.id)
    if not player:
        await update.message.reply_text(
            "⚠️ No tienes cuenta. Usa /start para registrarte."
        )
        return
    if player["status"] in ("banned", "suspended"):
        await update.message.reply_text("⛔ Tu cuenta está restringida.")
        return
    await update.message.reply_text(
        f"🏠 *Menú principal* — Hola, *{player['cr_name']}* 👋",
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
        f"🏠 *Menú principal* — Hola, *{name}* 👋",
        parse_mode="Markdown",
        reply_markup=kb_main_menu()
    )
