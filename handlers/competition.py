"""
Competencia v7:
- Efecto desvanecimiento (edit_message en vez de send)
- Captures de disputa sin duplicados
- match_id en callback, no en user_data (funciona desde /admin)
- Jobs persistentes con application
- Timeout 15 min / recordatorio 10 min
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import database as db
import services
from utils import (
    kb_game_modes, kb_main_menu, kb_in_queue, kb_compete_again,
    kb_match_result, kb_dispute_resolve, kb_confirm,
    kb_back_to_menu, is_business_hours,
    fmt_usd, fmt_ves, mode_label,
)
from config import (
    ADMIN_IDS, ARENAX_PAYMENT, ENTRY_FEE_USD, WIN_PRIZE_USD,
    GROUP_ID, TOPIC_MATCHMAKING_ID, TOPIC_RESULTS_ID,
    ADMIN_CHANNEL_ID, RESULT_TIMEOUT_MIN, RESULT_REMINDER_MIN,
)

logger = logging.getLogger(__name__)

SELECT_MODE           = 0
WAITING_PAYMENT       = 1
WAITING_DISPUTE_PROOF = 12
DISPUTE_REASON        = 11


# ── Canal admin ───────────────────────────────────────────────────────────────

async def notify_admin(bot, text, reply_markup=None, photo=None):
    target = ADMIN_CHANNEL_ID if ADMIN_CHANNEL_ID != 0 else ADMIN_IDS[0]
    try:
        if photo:
            await bot.send_photo(chat_id=target, photo=photo, caption=text,
                                  parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await bot.send_message(chat_id=target, text=text,
                                    parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error canal admin: {e}")
        if target != ADMIN_IDS[0]:
            try:
                if photo:
                    await bot.send_photo(chat_id=ADMIN_IDS[0], photo=photo, caption=text,
                                          parse_mode="Markdown", reply_markup=reply_markup)
                else:
                    await bot.send_message(chat_id=ADMIN_IDS[0], text=text,
                                            parse_mode="Markdown", reply_markup=reply_markup)
            except Exception as e2:
                logger.error(f"Error fallback DM admin: {e2}")


# ── Iniciar competencia ───────────────────────────────────────────────────────

async def start_compete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    ctx.user_data.clear()
    user   = update.effective_user
    player = db.get_player(user.id)

    if not player or player["status"] != "active":
        await update.callback_query.edit_message_text(
            "⚠️ Tu cuenta no está activa.", reply_markup=kb_back_to_menu()
        )
        return ConversationHandler.END

    if not is_business_hours():
        await update.callback_query.edit_message_text(
            "🕙 ArenaX opera de *10:00 am a 10:00 pm* (hora Venezuela).",
            parse_mode="Markdown", reply_markup=kb_back_to_menu()
        )
        return ConversationHandler.END

    try:
        win_limit = int(db.get_setting("win_limit_day") or "10")
    except Exception:
        win_limit = 10

    if player["wins_today"] >= win_limit:
        await update.callback_query.edit_message_text(
            f"🚫 *Límite diario alcanzado*\n\n"
            f"Llevas *{player['wins_today']} victorias* hoy.\n"
            f"El límite es *{win_limit}* por día.\n\n¡Vuelve mañana! 🏆",
            parse_mode="Markdown", reply_markup=kb_back_to_menu()
        )
        return ConversationHandler.END

    if db.is_in_queue(user.id):
        await update.callback_query.edit_message_text(
            "⏳ Ya estás en la cola esperando rival.", reply_markup=kb_in_queue()
        )
        return ConversationHandler.END

    active = db.get_active_match_for_player(user.id)
    if active:
        await update.callback_query.edit_message_text(
            f"⚔️ Tienes la *Partida #{active['id']}* en curso.\n¿Cuál fue el resultado?",
            parse_mode="Markdown", reply_markup=kb_match_result(active["id"])
        )
        return ConversationHandler.END

    await update.callback_query.edit_message_text(
        "🎮 *Selecciona el modo de juego:*",
        parse_mode="Markdown", reply_markup=kb_game_modes()
    )
    return SELECT_MODE


async def select_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    mode = update.callback_query.data.replace("mode_", "")
    from config import GAME_MODES
    if mode not in GAME_MODES:
        return SELECT_MODE

    ctx.user_data["game_mode"] = mode
    player  = db.get_player(update.effective_user.id)
    balance = player["balance_usd"]
    rate    = await services.get_bcv_rate()
    ctx.user_data["bcv_rate"] = rate

    if balance >= ENTRY_FEE_USD:
        await update.callback_query.edit_message_text(
            f"*Modo: {mode_label(mode)}*\n\n"
            f"💰 Tienes *{fmt_usd(balance)}* en tu balance.\n"
            f"¿Cómo deseas pagar la inscripción de *{fmt_usd(ENTRY_FEE_USD)}*?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"✅ Usar saldo ({fmt_usd(balance)})",
                                      callback_data="pay_from_balance")],
                [InlineKeyboardButton("💳 Pagar con pago móvil", callback_data="pay_mobile")],
                [InlineKeyboardButton("🔙 Volver", callback_data="menu_main")],
            ])
        )
    else:
        amount_ves = services.usd_to_ves(ENTRY_FEE_USD, rate)
        ctx.user_data["amount_ves"] = amount_ves
        p = ARENAX_PAYMENT
        instructions = db.get_text("payment_instructions")
        await update.callback_query.edit_message_text(
            f"*Modo: {mode_label(mode)}*\n\n{instructions}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏦 *Banco:* {p['bank']}\n"
            f"📱 *Teléfono:* `{p['phone']}`\n"
            f"🪪 *Cédula:* `{p['cedula']}`\n"
            f"👤 *Nombre:* {p['name']}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 *Inscripción:* {fmt_usd(ENTRY_FEE_USD)}\n"
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
    pay_id  = db.create_payment(user.id, mode, ENTRY_FEE_USD, ves, rate, file_id)
    player  = db.get_player(user.id)

    await update.message.reply_text(
        "✅ *Comprobante recibido.*\nEl administrador revisará tu pago en breve. ⏳",
        parse_mode="Markdown", reply_markup=kb_main_menu()
    )
    from utils import kb_payment_review
    await notify_admin(
        update.get_bot(),
        f"💳 *Pago pendiente #{pay_id}*\n"
        f"👤 {player['cr_name']} | {mode_label(mode)}\n"
        f"💵 {fmt_usd(ENTRY_FEE_USD)} = {fmt_ves(ves)}\n"
        f"📈 Tasa: {services.format_rate(rate)}",
        reply_markup=kb_payment_review(pay_id), photo=file_id
    )
    ctx.user_data.clear()
    return ConversationHandler.END


async def pay_from_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user   = update.effective_user
    mode   = ctx.user_data.get("game_mode", "1v1")
    rate   = ctx.user_data.get("bcv_rate", 0)
    player = db.get_player(user.id)

    if player["balance_usd"] < ENTRY_FEE_USD:
        await update.callback_query.edit_message_text(
            f"⚠️ Saldo insuficiente. Necesitas {fmt_usd(ENTRY_FEE_USD)}."
        )
        return ConversationHandler.END

    db.update_player_balance(user.id, -ENTRY_FEE_USD, f"Inscripción {mode_label(mode)}", "debit")
    pay_id = db.create_payment(user.id, mode, ENTRY_FEE_USD, 0, rate, "balance")
    db.update_payment_status(pay_id, "approved", user.id)

    await update.callback_query.edit_message_text(
        f"✅ *{fmt_usd(ENTRY_FEE_USD)} descontados de tu balance.*\n"
        f"Entrando en cola para {mode_label(mode)}... ⏳",
        parse_mode="Markdown"
    )
    ctx.user_data.clear()
    await try_match(update.get_bot(), user.id, mode, pay_id, application=ctx.application)
    return ConversationHandler.END


async def pay_mobile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    mode       = ctx.user_data.get("game_mode", "1v1")
    rate       = ctx.user_data.get("bcv_rate", 0)
    amount_ves = services.usd_to_ves(ENTRY_FEE_USD, rate)
    ctx.user_data["amount_ves"] = amount_ves
    p = ARENAX_PAYMENT
    await update.callback_query.edit_message_text(
        f"*Modo: {mode_label(mode)}*\n\n"
        f"🏦 *Banco:* {p['bank']}\n📱 *Teléfono:* `{p['phone']}`\n"
        f"🪪 *Cédula:* `{p['cedula']}`\n👤 *Nombre:* {p['name']}\n\n"
        f"💵 {fmt_usd(ENTRY_FEE_USD)} = *{fmt_ves(amount_ves)}*\n"
        f"📈 Tasa BCV: {services.format_rate(rate)}\n\n"
        f"📸 Envía el *capture* del comprobante:",
        parse_mode="Markdown"
    )
    return WAITING_PAYMENT


# ── Cola ──────────────────────────────────────────────────────────────────────

async def leave_queue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user = update.effective_user
    if not db.is_in_queue(user.id):
        await update.callback_query.edit_message_text(
            "ℹ️ Ya no estás en la cola.", reply_markup=kb_main_menu()
        )
        return
    db.remove_from_queue(user.id)
    db.update_player_balance(user.id, ENTRY_FEE_USD, "Reembolso por salir de la cola", "refund")
    player = db.get_player(user.id)
    await update.callback_query.edit_message_text(
        f"✅ Saliste de la cola.\n"
        f"💰 Reembolso: *{fmt_usd(ENTRY_FEE_USD)}*\n"
        f"Balance: *{fmt_usd(player['balance_usd'])}*",
        parse_mode="Markdown", reply_markup=kb_main_menu()
    )


# ── Matchmaking ───────────────────────────────────────────────────────────────

async def try_match(bot, telegram_id, game_mode, payment_id, application=None):
    opponent = db.find_match_in_queue(game_mode, telegram_id)

    if not opponent:
        db.add_to_queue(telegram_id, game_mode, payment_id)
        await bot.send_message(
            chat_id=telegram_id,
            text=f"⏳ *En cola — {mode_label(game_mode)}*\n\nBuscando oponente... 🎯",
            parse_mode="Markdown", reply_markup=kb_in_queue()
        )
        return

    p1 = db.get_player(telegram_id)
    p2 = db.get_player(opponent["telegram_id"])
    db.remove_from_queue(telegram_id)
    db.remove_from_queue(opponent["telegram_id"])
    match_id = db.create_match(telegram_id, opponent["telegram_id"], game_mode)
    rules    = db.get_text("match_rules")

    def kb_match(link, mid):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 Agregar amigo en Clash Royale", url=link)],
            [InlineKeyboardButton("🏆 Yo gané",  callback_data=f"result_win_{mid}"),
             InlineKeyboardButton("😞 Yo perdí", callback_data=f"result_lose_{mid}")],
        ])

    msg = (
        f"🔥 *¡Partida #{match_id} encontrada!*\n\n"
        f"🎮 Modo: {mode_label(game_mode)}\n"
        f"🏆 Premio: *{fmt_usd(WIN_PRIZE_USD)}* netos si ganas\n\n"
        f"👤 Tu oponente: *{{oponente}}*\n\n"
        f"{rules}\n\n"
        f"⏰ Tienes *{RESULT_TIMEOUT_MIN} minutos* para reportar."
    )

    await bot.send_message(
        chat_id=telegram_id,
        text=msg.format(oponente=p2["cr_name"]),
        parse_mode="Markdown",
        reply_markup=kb_match(p2["friend_link"], match_id)
    )
    await bot.send_message(
        chat_id=opponent["telegram_id"],
        text=msg.format(oponente=p1["cr_name"]),
        parse_mode="Markdown",
        reply_markup=kb_match(p1["friend_link"], match_id)
    )

    try:
        await bot.send_message(
            chat_id=GROUP_ID, message_thread_id=TOPIC_MATCHMAKING_ID,
            text=f"⚔️ *Partida #{match_id}*\n\n🎮 {mode_label(game_mode)}\n"
                 f"👤 {p1['cr_name']} vs {p2['cr_name']}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"No se pudo publicar en grupo: {e}")

    if application:
        job_data = {"match_id": match_id, "p1_id": telegram_id,
                    "p2_id": opponent["telegram_id"], "game_mode": game_mode}
        application.job_queue.run_once(
            _reminder_job, RESULT_REMINDER_MIN * 60,
            data=job_data, name=f"reminder_{match_id}"
        )
        application.job_queue.run_once(
            _timeout_job, RESULT_TIMEOUT_MIN * 60,
            data=job_data, name=f"timeout_{match_id}"
        )
    else:
        logger.warning(f"try_match sin application — timeout desactivado para #{match_id}")


# ── Jobs ──────────────────────────────────────────────────────────────────────

async def _reminder_job(context):
    data     = context.job.data
    match_id = data["match_id"]
    match    = db.get_match(match_id)
    if not match or match["status"] != "active":
        return
    for pid in [data["p1_id"], data["p2_id"]]:
        if db.get_match_report(match_id, pid) is None:
            try:
                await context.bot.send_message(
                    pid,
                    f"⏰ *Recordatorio — Partida #{match_id}*\n\n"
                    f"Te quedan *{RESULT_TIMEOUT_MIN - RESULT_REMINDER_MIN} minutos* para reportar.",
                    parse_mode="Markdown", reply_markup=kb_match_result(match_id)
                )
            except Exception as e:
                logger.error(f"Error recordatorio: {e}")


async def _timeout_job(context):
    data     = context.job.data
    match_id = data["match_id"]
    match    = db.get_match(match_id)
    if not match or match["status"] != "active":
        return
    await _resolve_timeout(context.bot, match_id, data["p1_id"], data["p2_id"], data["game_mode"])


async def _resolve_timeout(bot, match_id, p1_id, p2_id, game_mode):
    """Lógica de resolución por timeout — reutilizable para jobs persistentes."""
    r1 = db.get_match_report(match_id, p1_id)
    r2 = db.get_match_report(match_id, p2_id)

    if r1 is None and r2 is None:
        db.update_match_status(match_id, "voided")
        for pid in [p1_id, p2_id]:
            db.update_player_balance(pid, ENTRY_FEE_USD,
                                      f"Reembolso partida #{match_id} — tiempo agotado", "refund")
            try:
                await bot.send_message(
                    pid,
                    f"⏱ *Tiempo agotado — Partida #{match_id}*\n\n"
                    f"Ninguno reportó. 💰 Reembolso: *{fmt_usd(ENTRY_FEE_USD)}* a tu balance.",
                    parse_mode="Markdown", reply_markup=kb_compete_again()
                )
            except Exception as e:
                logger.error(f"Error reembolso timeout: {e}")
        return

    if r1 is not None and r2 is None:
        reporter_id, no_reporter_id, outcome = p1_id, p2_id, r1["outcome"]
    elif r2 is not None and r1 is None:
        reporter_id, no_reporter_id, outcome = p2_id, p1_id, r2["outcome"]
    else:
        return

    winner_id = reporter_id if outcome == "win" else no_reporter_id
    loser_id  = no_reporter_id if outcome == "win" else reporter_id
    await _finalize_match_auto(bot, match_id, winner_id, loser_id, game_mode)
    try:
        await bot.send_message(
            no_reporter_id,
            f"⏱ *Tiempo agotado — Partida #{match_id}*\n\n"
            f"No reportaste a tiempo. La partida fue asignada al oponente.",
            parse_mode="Markdown", reply_markup=kb_compete_again()
        )
    except Exception as e:
        logger.error(f"Error notificando timeout: {e}")


def _cancel_match_jobs(application, match_id):
    try:
        for name in [f"reminder_{match_id}", f"timeout_{match_id}"]:
            for j in application.job_queue.get_jobs_by_name(name):
                j.schedule_removal()
    except Exception as e:
        logger.warning(f"No se pudo cancelar job: {e}")


# ── Recuperación de partidas huérfanas al arrancar ────────────────────────────

async def recover_orphan_matches(bot):
    """
    Llamado al arrancar el bot.
    Resuelve partidas activas que quedaron huérfanas por un reinicio.
    """
    orphans = db.get_orphan_matches(RESULT_TIMEOUT_MIN)
    if not orphans:
        return
    logger.info(f"Recuperando {len(orphans)} partidas huérfanas...")
    for match in orphans:
        try:
            await _resolve_timeout(
                bot, match["id"],
                match["player1_id"], match["player2_id"], match["game_mode"]
            )
            logger.info(f"Partida #{match['id']} resuelta (huérfana)")
        except Exception as e:
            logger.error(f"Error recuperando partida #{match['id']}: {e}")


# ── Sistema "Yo gané / Yo perdí" ─────────────────────────────────────────────

async def handle_result(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    data     = update.callback_query.data
    user     = update.effective_user
    parts    = data.split("_")
    outcome  = parts[1]
    match_id = int(parts[2])

    match = db.get_match(match_id)
    if not match or match["status"] not in ("active",):
        await update.callback_query.edit_message_text(
            "⚠️ Esta partida ya fue procesada.", reply_markup=kb_compete_again()
        )
        return

    if db.get_match_report(match_id, user.id):
        await update.callback_query.answer(
            "Ya reportaste tu resultado. Esperando al oponente...", show_alert=True
        )
        return

    db.set_match_report(match_id, user.id, outcome)
    other_id     = match["player2_id"] if match["player1_id"] == user.id else match["player1_id"]
    other_report = db.get_match_report(match_id, other_id)

    if other_report is None:
        await update.callback_query.edit_message_text(
            f"✅ Reportaste: *{'🏆 Victoria' if outcome == 'win' else '😞 Derrota'}*\n\n"
            f"Esperando que tu oponente reporte...\n"
            f"⏰ Límite: {RESULT_TIMEOUT_MIN} min desde el inicio.",
            parse_mode="Markdown"
        )
        return

    other_outcome = other_report["outcome"]
    _cancel_match_jobs(ctx.application, match_id)

    # Caso 1: coincidencia → automático
    if (outcome == "win" and other_outcome == "lose") or \
       (outcome == "lose" and other_outcome == "win"):
        winner_id = user.id if outcome == "win" else other_id
        loser_id  = other_id if outcome == "win" else user.id
        await _finalize_match_auto(update.get_bot(), match_id, winner_id, loser_id, match["game_mode"])
        return

    # Caso 2: ambos perdieron → anulación automática
    if outcome == "lose" and other_outcome == "lose":
        db.update_match_status(match_id, "voided")
        for pid in [user.id, other_id]:
            db.update_player_balance(pid, ENTRY_FEE_USD,
                                      f"Reembolso partida #{match_id} — ambos reportaron derrota", "refund")
            try:
                await update.get_bot().send_message(
                    pid,
                    f"🤝 *Partida #{match_id} — Ambos reportaron derrota*\n\n"
                    f"💰 Reembolso: *{fmt_usd(ENTRY_FEE_USD)}* a tu balance.",
                    parse_mode="Markdown", reply_markup=kb_compete_again()
                )
            except Exception as e:
                logger.error(f"Error reembolso ambos-perdieron: {e}")
        return

    # Caso 3: ambos ganaron → disputa
    await _open_dispute_both_won(update.get_bot(), match_id, match, user.id, other_id)


async def _finalize_match_auto(bot, match_id, winner_id, loser_id, game_mode):
    db.finalize_match(match_id, winner_id)
    total_credit = WIN_PRIZE_USD + ENTRY_FEE_USD
    db.update_player_balance(winner_id, total_credit,
                              f"Victoria Partida #{match_id}", "prize", match_id)
    winner = db.get_player(winner_id)
    loser  = db.get_player(loser_id)

    await bot.send_message(
        winner_id,
        f"🏆 *¡Victoria en Partida #{match_id}!*\n\n"
        f"💰 Premio neto: *{fmt_usd(WIN_PRIZE_USD)}*\n"
        f"💵 Inscripción recuperada: *{fmt_usd(ENTRY_FEE_USD)}*\n"
        f"✅ *Total: {fmt_usd(total_credit)}*\n\n"
        f"Balance: {fmt_usd(winner['balance_usd'])}",
        parse_mode="Markdown", reply_markup=kb_compete_again()
    )
    await bot.send_message(
        loser_id,
        f"😞 *Derrota en Partida #{match_id}*\n\n¡La próxima es tuya! 💪",
        parse_mode="Markdown", reply_markup=kb_compete_again()
    )
    try:
        await bot.send_message(
            chat_id=GROUP_ID, message_thread_id=TOPIC_RESULTS_ID,
            text=f"🏆 *Resultado — Partida #{match_id}*\n\n"
                 f"🥇 Ganador: *{winner['cr_name']}*\n"
                 f"😞 Perdedor: {loser['cr_name']}\n"
                 f"🎮 {mode_label(game_mode)}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"No se pudo publicar resultado: {e}")


async def _open_dispute_both_won(bot, match_id, match, p_id, other_id):
    reason     = "Ambos jugadores reportaron victoria"
    dispute_id = db.create_dispute(match_id, p_id, reason)

    for pid in [p_id, other_id]:
        try:
            await bot.send_message(
                pid,
                f"⚠️ *Conflicto — Partida #{match_id}*\n\n"
                f"Ambos reportaron victoria. 🤔\n\n"
                f"📸 Presiona el botón y envía tu capture de resultado:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📸 Enviar mi capture",
                                         callback_data=f"submit_dispute_proof_{match_id}")
                ]])
            )
        except Exception as e:
            logger.error(f"Error notificando disputa: {e}")

    p1 = db.get_player(match["player1_id"])
    p2 = db.get_player(match["player2_id"])
    await notify_admin(
        bot,
        f"⚖️ *Disputa #{dispute_id} — Partida #{match_id}*\n\n"
        f"🎮 {mode_label(match['game_mode'])}\n"
        f"👤 {p1['cr_name']} vs {p2['cr_name']}\n\n"
        f"⚠️ Ambos reportaron victoria.\n"
        f"Esperando captures de ambos jugadores...\n\n"
        f"_(Los botones aparecerán cuando ambos envíen sus captures)_",
        parse_mode="Markdown"
    )


# ── Capture de disputa ────────────────────────────────────────────────────────
# match_id viene del callback data — no depende de user_data
# Funciona correctamente incluso después de /admin

async def start_dispute_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    raw = update.callback_query.data.replace("submit_dispute_proof_", "")
    try:
        match_id = int(raw)
    except ValueError:
        await update.callback_query.answer("Error.", show_alert=True)
        return ConversationHandler.END

    ctx.user_data["dispute_proof_match_id"] = match_id
    await update.callback_query.message.reply_text(
        f"📸 Envía tu capture de resultado de la *Partida #{match_id}*:",
        parse_mode="Markdown"
    )
    return WAITING_DISPUTE_PROOF


async def receive_dispute_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Recibe capture de disputa.
    Cuando llega el PRIMER capture: notifica al admin que está esperando el segundo.
    Cuando llega el SEGUNDO capture: envía ambos al admin CON el panel de decisión.
    Sin duplicados.
    """
    user     = update.effective_user
    file_id  = update.message.photo[-1].file_id
    match_id = ctx.user_data.get("dispute_proof_match_id")

    if not match_id:
        await update.message.reply_text("⚠️ Error. Usa /menu")
        return ConversationHandler.END

    match  = db.get_match(match_id)
    player = db.get_player(user.id)

    if not match:
        await update.message.reply_text("⚠️ Partida no encontrada.")
        return ConversationHandler.END

    db.set_match_result_proof(match_id, user.id, file_id)
    await update.message.reply_text(
        "✅ Capture recibido. El administrador lo revisará junto con el de tu oponente.",
        reply_markup=kb_main_menu()
    )

    other_id = match["player2_id"] if match["player1_id"] == user.id else match["player1_id"]
    other    = db.get_player(other_id)

    # Refrescar match para ver si el otro ya envió
    match     = db.get_match(match_id)
    p1_proof  = match["result_proof_p1"]
    p2_proof  = match["result_proof_p2"]

    disputes   = db.get_open_disputes()
    dispute    = next((d for d in disputes if d["match_id"] == match_id), None)
    dispute_id = dispute["id"] if dispute else 0

    p1 = db.get_player(match["player1_id"])
    p2 = db.get_player(match["player2_id"])

    if p1_proof and p2_proof:
        # Ambos enviaron → mandar los dos captures + panel de decisión
        # Primero capture de J1 (sin botones)
        await notify_admin(
            update.get_bot(),
            f"📸 *{p1['cr_name']}* (J1) — Partida #{match_id}",
            photo=p1_proof
        )
        # Segundo capture de J2 + panel de decisión
        await notify_admin(
            update.get_bot(),
            f"📸 *{p2['cr_name']}* (J2) — Partida #{match_id}\n\n"
            f"⚖️ *¿Quién ganó la Partida #{match_id}?*",
            photo=p2_proof,
            reply_markup=kb_dispute_resolve(dispute_id, match["player1_id"], match["player2_id"])
        )
    else:
        # Solo uno envió — notificar quién falta sin mostrar el capture aún
        who_left = other["cr_name"]
        await notify_admin(
            update.get_bot(),
            f"⚖️ *Disputa #{dispute_id} — Partida #{match_id}*\n\n"
            f"✅ *{player['cr_name']}* envió su capture.\n"
            f"⏳ Esperando capture de *{who_left}*..."
        )

    ctx.user_data.pop("dispute_proof_match_id", None)
    return ConversationHandler.END


# ── Disputa manual ────────────────────────────────────────────────────────────

async def open_dispute(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    try:
        match_id = int(update.callback_query.data.replace("dispute_", ""))
    except ValueError:
        await update.callback_query.answer("Error.", show_alert=True)
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
        await update.message.reply_text("⚠️ Error. Usa /menu")
        return ConversationHandler.END
    match = db.get_match(match_id)
    if not match:
        await update.message.reply_text("⚠️ Partida no encontrada.")
        return ConversationHandler.END
    dispute_id = db.create_dispute(match_id, user.id, reason)
    player     = db.get_player(user.id)
    await update.message.reply_text(
        f"⚖️ *Disputa #{dispute_id} abierta.*",
        parse_mode="Markdown", reply_markup=kb_main_menu()
    )
    opp_id = match["player2_id"] if match["player1_id"] == user.id else match["player1_id"]
    try:
        await update.get_bot().send_message(opp_id, f"⚠️ Tu oponente abrió una disputa en Partida #{match_id}.")
    except Exception:
        pass
    await notify_admin(
        update.get_bot(),
        f"⚖️ *Disputa #{dispute_id}*\n\n"
        f"Partida #{match_id} | {mode_label(match['game_mode'])}\n"
        f"Por: *{player['cr_name']}*\n\nMotivo: {reason}",
        reply_markup=kb_dispute_resolve(dispute_id, match["player1_id"], match["player2_id"])
    )
    ctx.user_data.clear()
    return ConversationHandler.END
