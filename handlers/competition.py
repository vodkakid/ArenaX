"""
Handlers de competencia: modo, pago, cola, matchmaking, resultados, disputas.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import database as db
import services
from utils import (kb_game_modes, kb_main_menu, kb_back_to_menu, kb_in_queue,
                   kb_report_or_dispute, kb_dispute_resolve, is_business_hours,
                   fmt_usd, fmt_ves, mode_label)
from config import (ADMIN_IDS, ARENAX_PAYMENT, ENTRY_FEE_USD, PRIZE_POOL_PCT,
                    GROUP_ID, TOPIC_MATCHMAKING_ID, TOPIC_RESULTS_ID)

logger = logging.getLogger(__name__)

SELECT_MODE, WAITING_PAYMENT = range(2)
WAITING_RESULT_PROOF = 10
DISPUTE_REASON       = 11


# ── Iniciar competencia ───────────────────────────────────────────────────────

async def start_compete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user   = update.effective_user
    player = db.get_player(user.id)

    if not player or player["status"] != "active":
        await update.callback_query.message.reply_text("⚠️ Tu cuenta no está activa.")
        return ConversationHandler.END

    if not is_business_hours():
        await update.callback_query.edit_message_text(
            "🕙 ArenaX opera de *10:00 am a 10:00 pm* (hora Venezuela).",
            parse_mode="Markdown", reply_markup=kb_back_to_menu()
        )
        return ConversationHandler.END

    if db.is_in_queue(user.id):
        await update.callback_query.edit_message_text(
            "⏳ Ya estás en la cola esperando un oponente.\n"
            "Serás notificado cuando se encuentre un rival.",
            reply_markup=kb_in_queue()
        )
        return ConversationHandler.END

    active_match = db.get_active_match_for_player(user.id)
    if active_match:
        await update.callback_query.edit_message_text(
            "⚔️ Ya tienes una partida activa. Reporta el resultado:",
            reply_markup=kb_report_or_dispute(active_match["id"])
        )
        return ConversationHandler.END

    await update.callback_query.edit_message_text(
        "🎮 *Selecciona el modo de juego:*",
        parse_mode="Markdown",
        reply_markup=kb_game_modes()
    )
    return SELECT_MODE


async def select_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    mode = update.callback_query.data.replace("mode_", "")

    from config import GAME_MODES
    if mode not in GAME_MODES:
        await update.callback_query.answer("Modo no válido")
        return SELECT_MODE

    ctx.user_data["game_mode"] = mode
    rate = await services.get_bcv_rate()

    if rate <= 0:
        await update.callback_query.message.reply_text(
            "⚠️ No se pudo obtener la tasa BCV. Intenta en unos minutos."
        )
        return ConversationHandler.END

    amount_ves = services.usd_to_ves(ENTRY_FEE_USD, rate)
    ctx.user_data["bcv_rate"]   = rate
    ctx.user_data["amount_ves"] = amount_ves

    p = ARENAX_PAYMENT
    instructions = db.get_text("payment_instructions")
    await update.callback_query.edit_message_text(
        f"*Modo: {mode_label(mode)}*\n\n"
        f"{instructions}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏦 *Banco:* {p['bank']}\n"
        f"📱 *Teléfono:* `{p['phone']}`\n"
        f"🪪 *Cédula:* `{p['cedula']}`\n"
        f"👤 *Nombre:* {p['name']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 *Monto:* {fmt_usd(ENTRY_FEE_USD)}\n"
        f"📈 *Tasa BCV:* {services.format_rate(rate)}\n"
        f"💰 *A pagar:* *{fmt_ves(amount_ves)}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📸 Realiza el pago y envía el *capture* como foto:",
        parse_mode="Markdown"
    )
    return WAITING_PAYMENT


async def receive_payment_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    file_id = update.message.photo[-1].file_id
    mode    = ctx.user_data.get("game_mode", "1v1")
    rate    = ctx.user_data.get("bcv_rate", 0)
    ves     = ctx.user_data.get("amount_ves", 0)

    pay_id = db.create_payment(user.id, mode, ENTRY_FEE_USD, ves, rate, file_id)

    await update.message.reply_text(
        "✅ *Comprobante recibido.*\n"
        "El administrador revisará tu pago y te notificará al ser aprobado. ⏳",
        parse_mode="Markdown",
        reply_markup=kb_main_menu()
    )

    player = db.get_player(user.id)
    for admin_id in ADMIN_IDS:
        try:
            from utils import kb_payment_review
            await ctx.bot.send_photo(
                chat_id    = admin_id,
                photo      = file_id,
                caption    = (
                    f"💳 *Pago pendiente #{pay_id}*\n"
                    f"👤 {player['cr_name']} (@{player['username'] or user.id})\n"
                    f"🎮 {mode_label(mode)}\n"
                    f"💵 {fmt_usd(ENTRY_FEE_USD)} = {fmt_ves(ves)}\n"
                    f"📈 Tasa: {services.format_rate(rate)}"
                ),
                parse_mode = "Markdown",
                reply_markup = kb_payment_review(pay_id)
            )
        except Exception as e:
            logger.error(f"Error notificando pago a admin {admin_id}: {e}")

    ctx.user_data.clear()
    return ConversationHandler.END


# ── Salir de la cola ──────────────────────────────────────────────────────────

async def leave_queue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user = update.effective_user

    if not db.is_in_queue(user.id):
        await update.callback_query.edit_message_text(
            "ℹ️ Ya no estás en la cola.",
            reply_markup=kb_main_menu()
        )
        return

    # Buscar el pago asociado para reembolsar
    queue_entry = db.get_queue_entry(user.id)
    db.remove_from_queue(user.id)

    # Reembolsar la inscripción
    db.update_player_balance(
        user.id, ENTRY_FEE_USD,
        "Reembolso por salir de la cola", "refund"
    )

    player = db.get_player(user.id)
    await update.callback_query.edit_message_text(
        f"✅ *Saliste de la cola.*\n\n"
        f"💰 Se reembolsaron *{fmt_usd(ENTRY_FEE_USD)}* a tu balance.\n"
        f"Balance actual: *{fmt_usd(player['balance_usd'])}*",
        parse_mode="Markdown",
        reply_markup=kb_main_menu()
    )


# ── Matchmaking ───────────────────────────────────────────────────────────────

async def try_match(bot, telegram_id: int, game_mode: str, payment_id: int):
    opponent = db.find_match_in_queue(game_mode, telegram_id)

    if not opponent:
        db.add_to_queue(telegram_id, game_mode, payment_id)
        await bot.send_message(
            chat_id    = telegram_id,
            text       = (
                f"⏳ *Buscando oponente...*\n\n"
                f"Modo: {mode_label(game_mode)}\n"
                f"Estás en la cola. Te avisamos cuando encontremos rival. 🎯"
            ),
            parse_mode = "Markdown",
            reply_markup = kb_in_queue()
        )
        return

    p1 = db.get_player(telegram_id)
    p2 = db.get_player(opponent["telegram_id"])

    db.remove_from_queue(telegram_id)
    db.remove_from_queue(opponent["telegram_id"])

    prize    = round(ENTRY_FEE_USD * 2 * PRIZE_POOL_PCT, 2)
    match_id = db.create_match(telegram_id, opponent["telegram_id"], game_mode, prize)
    rules    = db.get_text("match_rules")

    msg = (
        f"🔥 *¡Emparejamiento encontrado!*\n\n"
        f"⚔️ Modo: {mode_label(game_mode)}\n"
        f"🏆 Premio al ganador: {fmt_usd(prize)}\n\n"
        f"{{oponent_name}}\n"
        f"🔗 Link de amistad: `{{friend_link}}`\n\n"
        f"{rules}"
    )

    await bot.send_message(
        chat_id      = telegram_id,
        text         = msg.format(
            oponent_name=f"👤 Tu oponente: *{p2['cr_name']}*",
            friend_link=p2['friend_link']
        ),
        parse_mode   = "Markdown",
        reply_markup = kb_report_or_dispute(match_id)
    )
    await bot.send_message(
        chat_id      = opponent["telegram_id"],
        text         = msg.format(
            oponent_name=f"👤 Tu oponente: *{p1['cr_name']}*",
            friend_link=p1['friend_link']
        ),
        parse_mode   = "Markdown",
        reply_markup = kb_report_or_dispute(match_id)
    )

    # Publicar en grupo oficial — tema Emparejamientos
    try:
        await bot.send_message(
            chat_id           = GROUP_ID,
            message_thread_id = TOPIC_MATCHMAKING_ID,
            text              = (
                f"⚔️ *¡Nueva partida en curso!*\n\n"
                f"🎮 {mode_label(game_mode)}\n"
                f"👤 {p1['cr_name']} vs {p2['cr_name']}\n"
                f"🏆 Premio: {fmt_usd(prize)}"
            ),
            parse_mode = "Markdown"
        )
    except Exception as e:
        logger.warning(f"No se pudo publicar emparejamiento en grupo: {e}")


# ── Reportar resultado ────────────────────────────────────────────────────────

async def report_result_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    match_id = int(update.callback_query.data.replace("report_result_", ""))
    ctx.user_data["reporting_match_id"] = match_id
    await update.callback_query.message.reply_text(
        "🏆 Envía el *capture* de la pantalla de victoria:",
        parse_mode="Markdown"
    )
    return WAITING_RESULT_PROOF


async def receive_result_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    file_id  = update.message.photo[-1].file_id
    match_id = ctx.user_data.get("reporting_match_id")
    match    = db.get_match(match_id)
    player   = db.get_player(user.id)

    if not match or match["status"] != "active":
        await update.message.reply_text("⚠️ Esta partida ya no está activa.")
        return ConversationHandler.END

    db.set_match_result_proof(match_id, user.id, file_id)

    await update.message.reply_text(
        "✅ Capture recibido. El administrador verificará el resultado.",
        reply_markup=kb_main_menu()
    )

    for admin_id in ADMIN_IDS:
        try:
            from utils import kb_result_review
            await ctx.bot.send_photo(
                chat_id    = admin_id,
                photo      = file_id,
                caption    = (
                    f"🏆 *Resultado — Partida #{match_id}*\n"
                    f"👤 Reportado por: *{player['cr_name']}*\n"
                    f"🎮 {mode_label(match['game_mode'])}\n"
                    f"💰 Premio: {fmt_usd(match['prize_usd'])}"
                ),
                parse_mode   = "Markdown",
                reply_markup = kb_result_review(match_id, user.id)
            )
        except Exception as e:
            logger.error(f"Error notificando resultado a admin: {e}")

    ctx.user_data.clear()
    return ConversationHandler.END


# ── Disputas ──────────────────────────────────────────────────────────────────

async def open_dispute(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    raw = update.callback_query.data.replace("dispute_", "")
    try:
        match_id = int(raw)
    except ValueError:
        await update.callback_query.answer("Error al procesar la disputa.", show_alert=True)
        return ConversationHandler.END

    ctx.user_data["dispute_match_id"] = match_id
    await update.callback_query.message.reply_text(
        "⚠️ *Abrir disputa*\n\nDescribe brevemente qué pasó:",
        parse_mode="Markdown"
    )
    return DISPUTE_REASON


async def submit_dispute(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    match_id = ctx.user_data.get("dispute_match_id")
    reason   = update.message.text[:500]

    if not match_id:
        await update.message.reply_text("⚠️ Error: no se encontró la partida. Usa /menu")
        return ConversationHandler.END

    match = db.get_match(match_id)
    if not match:
        await update.message.reply_text("⚠️ Partida no encontrada.")
        return ConversationHandler.END

    dispute_id = db.create_dispute(match_id, user.id, reason)
    player     = db.get_player(user.id)

    await update.message.reply_text(
        f"⚖️ *Disputa #{dispute_id} abierta.*\n"
        "El administrador revisará y notificará a ambos jugadores.",
        parse_mode="Markdown",
        reply_markup=kb_main_menu()
    )

    # Notificar al oponente
    opp_id = match["player2_id"] if match["player1_id"] == user.id else match["player1_id"]
    try:
        await ctx.bot.send_message(
            opp_id,
            f"⚠️ Tu oponente abrió una *disputa* en la partida #{match_id}.\n"
            f"El administrador tomará una decisión pronto.",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    # Notificar a admins
    for admin_id in ADMIN_IDS:
        try:
            await ctx.bot.send_message(
                chat_id      = admin_id,
                text         = (
                    f"⚖️ *Nueva disputa #{dispute_id}*\n\n"
                    f"Partida: #{match_id} | {mode_label(match['game_mode'])}\n"
                    f"Reportado por: *{player['cr_name']}*\n\n"
                    f"Motivo: {reason}"
                ),
                parse_mode   = "Markdown",
                reply_markup = kb_dispute_resolve(
                    dispute_id, match["player1_id"], match["player2_id"]
                )
            )
        except Exception as e:
            logger.error(f"Error notificando disputa a admin: {e}")

    ctx.user_data.clear()
    return ConversationHandler.END
