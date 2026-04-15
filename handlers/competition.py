"""
Competencia v6.1 — Correcciones críticas:
- Link amistad como botón URL que abre CR directamente
- Timeout funciona correctamente (application pasado como parámetro)
- Botón "salir cola" desaparece al emparejar
- Capture de disputa completamente separado del flow de pago
- Verificación de límite de victorias al competir
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import database as db
import services
from utils import (
    kb_game_modes, kb_main_menu, kb_in_queue, kb_compete_again,
    kb_match_result, kb_result_review, kb_dispute_resolve,
    kb_confirm, kb_back_to_menu, is_business_hours,
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
WAITING_RESULT_PROOF  = 10
DISPUTE_REASON        = 11
WAITING_DISPUTE_PROOF = 12  # ← Estado separado para capturas de disputa


# ── Canal admin ───────────────────────────────────────────────────────────────

async def notify_admin(bot, text, reply_markup=None, photo=None):
    target = ADMIN_CHANNEL_ID if ADMIN_CHANNEL_ID != 0 else ADMIN_IDS[0]
    try:
        if photo:
            await bot.send_photo(
                chat_id=target, photo=photo, caption=text,
                parse_mode="Markdown", reply_markup=reply_markup
            )
        else:
            await bot.send_message(
                chat_id=target, text=text,
                parse_mode="Markdown", reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Error canal admin: {e}")
        if target != ADMIN_IDS[0]:
            try:
                if photo:
                    await bot.send_photo(
                        chat_id=ADMIN_IDS[0], photo=photo, caption=text,
                        parse_mode="Markdown", reply_markup=reply_markup
                    )
                else:
                    await bot.send_message(
                        chat_id=ADMIN_IDS[0], text=text,
                        parse_mode="Markdown", reply_markup=reply_markup
                    )
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
            "⚠️ Tu cuenta no está activa. Contacta al administrador.",
            reply_markup=kb_back_to_menu()
        )
        return ConversationHandler.END

    if not is_business_hours():
        await update.callback_query.edit_message_text(
            "🕙 ArenaX opera de *10:00 am a 10:00 pm* (hora Venezuela).",
            parse_mode="Markdown",
            reply_markup=kb_back_to_menu()
        )
        return ConversationHandler.END

    # ── Verificar límite de victorias del día ─────────────────────────────────
    try:
        win_limit = int(db.get_setting("win_limit_day") or "10")
    except Exception:
        win_limit = 10

    if player["wins_today"] >= win_limit:
        await update.callback_query.edit_message_text(
            f"🚫 *Límite diario alcanzado*\n\n"
            f"Llevas *{player['wins_today']} victorias* hoy.\n"
            f"El límite es de *{win_limit} victorias* por día.\n\n"
            f"¡Vuelve mañana! 🏆",
            parse_mode="Markdown",
            reply_markup=kb_back_to_menu()
        )
        return ConversationHandler.END

    if db.is_in_queue(user.id):
        await update.callback_query.edit_message_text(
            "⏳ Ya estás en la cola esperando rival.",
            reply_markup=kb_in_queue()
        )
        return ConversationHandler.END

    active = db.get_active_match_for_player(user.id)
    if active:
        await update.callback_query.edit_message_text(
            f"⚔️ Tienes la *Partida #{active['id']}* en curso.\n"
            f"¿Cuál fue el resultado?",
            parse_mode="Markdown",
            reply_markup=kb_match_result(active["id"])
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
                [InlineKeyboardButton(
                    f"✅ Usar saldo ({fmt_usd(balance)})",
                    callback_data="pay_from_balance"
                )],
                [InlineKeyboardButton(
                    "💳 Pagar con pago móvil",
                    callback_data="pay_mobile"
                )],
                [InlineKeyboardButton("🔙 Volver", callback_data="menu_main")],
            ])
        )
    else:
        amount_ves = services.usd_to_ves(ENTRY_FEE_USD, rate)
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
            f"💵 *Inscripción:* {fmt_usd(ENTRY_FEE_USD)}\n"
            f"📈 *Tasa BCV:* {services.format_rate(rate)}\n"
            f"💰 *A pagar:* *{fmt_ves(amount_ves)}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📸 Realiza el pago y envía el *capture* como foto:",
            parse_mode="Markdown"
        )
    return WAITING_PAYMENT


async def receive_payment_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Recibe capture de PAGO — solo si estamos en estado WAITING_PAYMENT."""
    user    = update.effective_user
    file_id = update.message.photo[-1].file_id
    mode    = ctx.user_data.get("game_mode", "1v1")
    rate    = ctx.user_data.get("bcv_rate", 0)
    ves     = ctx.user_data.get("amount_ves", 0)

    pay_id = db.create_payment(user.id, mode, ENTRY_FEE_USD, ves, rate, file_id)
    player = db.get_player(user.id)

    await update.message.reply_text(
        "✅ *Comprobante recibido.*\n"
        "El administrador revisará tu pago en breve. ⏳",
        parse_mode="Markdown",
        reply_markup=kb_main_menu()
    )

    from utils import kb_payment_review
    await notify_admin(
        update.get_bot(),
        f"💳 *Pago pendiente #{pay_id}*\n"
        f"👤 {player['cr_name']} | {mode_label(mode)}\n"
        f"💵 {fmt_usd(ENTRY_FEE_USD)} = {fmt_ves(ves)}\n"
        f"📈 Tasa: {services.format_rate(rate)}",
        reply_markup=kb_payment_review(pay_id),
        photo=file_id
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

    db.update_player_balance(
        user.id, -ENTRY_FEE_USD,
        f"Inscripción {mode_label(mode)}", "debit"
    )
    pay_id = db.create_payment(user.id, mode, ENTRY_FEE_USD, 0, rate, "balance")
    db.update_payment_status(pay_id, "approved", user.id)

    await update.callback_query.edit_message_text(
        f"✅ *{fmt_usd(ENTRY_FEE_USD)} descontados de tu balance.*\n"
        f"Entrando en cola para {mode_label(mode)}... ⏳",
        parse_mode="Markdown"
    )
    ctx.user_data.clear()
    await try_match(
        update.get_bot(), user.id, mode, pay_id,
        application=ctx.application
    )
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
        f"🏦 *Banco:* {p['bank']}\n"
        f"📱 *Teléfono:* `{p['phone']}`\n"
        f"🪪 *Cédula:* `{p['cedula']}`\n"
        f"👤 *Nombre:* {p['name']}\n\n"
        f"💵 {fmt_usd(ENTRY_FEE_USD)} = *{fmt_ves(amount_ves)}*\n"
        f"📈 Tasa BCV: {services.format_rate(rate)}\n\n"
        f"📸 Envía el *capture* del comprobante:",
        parse_mode="Markdown"
    )
    return WAITING_PAYMENT


# ── Salir de cola ─────────────────────────────────────────────────────────────

async def leave_queue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user = update.effective_user

    # Verificar que sigue en cola (no emparejado)
    if not db.is_in_queue(user.id):
        await update.callback_query.edit_message_text(
            "ℹ️ Ya no estás en la cola.",
            reply_markup=kb_main_menu()
        )
        return

    db.remove_from_queue(user.id)
    db.update_player_balance(
        user.id, ENTRY_FEE_USD,
        "Reembolso por salir de la cola", "refund"
    )
    player = db.get_player(user.id)
    await update.callback_query.edit_message_text(
        f"✅ Saliste de la cola.\n"
        f"💰 Reembolso: *{fmt_usd(ENTRY_FEE_USD)}*\n"
        f"Balance: *{fmt_usd(player['balance_usd'])}*",
        parse_mode="Markdown",
        reply_markup=kb_main_menu()
    )


# ── Matchmaking ───────────────────────────────────────────────────────────────

async def try_match(bot, telegram_id, game_mode, payment_id, application=None):
    """
    application debe pasarse para que los jobs de timeout funcionen.
    """
    opponent = db.find_match_in_queue(game_mode, telegram_id)

    if not opponent:
        db.add_to_queue(telegram_id, game_mode, payment_id)
        await bot.send_message(
            chat_id      = telegram_id,
            text         = (
                f"⏳ *En cola — {mode_label(game_mode)}*\n\n"
                f"Buscando oponente... Te avisamos al encontrar uno. 🎯"
            ),
            parse_mode   = "Markdown",
            reply_markup = kb_in_queue()
        )
        return

    p1 = db.get_player(telegram_id)
    p2 = db.get_player(opponent["telegram_id"])

    db.remove_from_queue(telegram_id)
    db.remove_from_queue(opponent["telegram_id"])

    match_id = db.create_match(telegram_id, opponent["telegram_id"], game_mode)
    rules    = db.get_text("match_rules")

    # ── Botones: link amistad como URL + resultado ────────────────────────────
    def kb_match(oponent_link: str, mid: int):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "👤 Agregar amigo en Clash Royale",
                url=oponent_link
            )],
            [InlineKeyboardButton("🏆 Yo gané",  callback_data=f"result_win_{mid}"),
             InlineKeyboardButton("😞 Yo perdí", callback_data=f"result_lose_{mid}")],
        ])

    msg_base = (
        f"🔥 *¡Partida #{match_id} encontrada!*\n\n"
        f"🎮 Modo: {mode_label(game_mode)}\n"
        f"🏆 Premio: *{fmt_usd(WIN_PRIZE_USD)}* netos si ganas\n\n"
        f"👤 Tu oponente: *{{oponente}}*\n\n"
        f"{rules}\n\n"
        f"⏰ Tienes *{RESULT_TIMEOUT_MIN} minutos* para reportar."
    )

    # Enviar a J1 — el botón del link abre el perfil de J2
    await bot.send_message(
        chat_id      = telegram_id,
        text         = msg_base.format(oponente=p2["cr_name"]),
        parse_mode   = "Markdown",
        reply_markup = kb_match(p2["friend_link"], match_id)
    )
    # Enviar a J2 — el botón del link abre el perfil de J1
    await bot.send_message(
        chat_id      = opponent["telegram_id"],
        text         = msg_base.format(oponente=p1["cr_name"]),
        parse_mode   = "Markdown",
        reply_markup = kb_match(p1["friend_link"], match_id)
    )

    # Publicar en grupo
    try:
        await bot.send_message(
            chat_id           = GROUP_ID,
            message_thread_id = TOPIC_MATCHMAKING_ID,
            text              = (
                f"⚔️ *Partida #{match_id}*\n\n"
                f"🎮 {mode_label(game_mode)}\n"
                f"👤 {p1['cr_name']} vs {p2['cr_name']}"
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"No se pudo publicar en grupo: {e}")

    # ── Jobs de timeout — requiere application ────────────────────────────────
    if application:
        job_data = {
            "match_id": match_id,
            "p1_id":    telegram_id,
            "p2_id":    opponent["telegram_id"],
            "game_mode": game_mode,
        }
        application.job_queue.run_once(
            _reminder_job,
            RESULT_REMINDER_MIN * 60,
            data=job_data,
            name=f"reminder_{match_id}"
        )
        application.job_queue.run_once(
            _timeout_job,
            RESULT_TIMEOUT_MIN * 60,
            data=job_data,
            name=f"timeout_{match_id}"
        )
    else:
        logger.warning(f"try_match llamado sin application — timeout desactivado para partida #{match_id}")


# ── Jobs de timeout ───────────────────────────────────────────────────────────

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
                    f"Te quedan *{RESULT_TIMEOUT_MIN - RESULT_REMINDER_MIN} minutos* "
                    f"para reportar el resultado.",
                    parse_mode="Markdown",
                    reply_markup=kb_match_result(match_id)
                )
            except Exception as e:
                logger.error(f"Error recordatorio: {e}")


async def _timeout_job(context):
    data     = context.job.data
    match_id = data["match_id"]
    match    = db.get_match(match_id)
    if not match or match["status"] != "active":
        return

    p1_id = data["p1_id"]
    p2_id = data["p2_id"]
    r1    = db.get_match_report(match_id, p1_id)
    r2    = db.get_match_report(match_id, p2_id)

    if r1 is None and r2 is None:
        # Nadie reportó → reembolso
        db.update_match_status(match_id, "voided")
        for pid in [p1_id, p2_id]:
            db.update_player_balance(
                pid, ENTRY_FEE_USD,
                f"Reembolso partida #{match_id} — tiempo agotado", "refund"
            )
            try:
                await context.bot.send_message(
                    pid,
                    f"⏱ *Tiempo agotado — Partida #{match_id}*\n\n"
                    f"Ninguno reportó el resultado.\n"
                    f"💰 Reembolso: *{fmt_usd(ENTRY_FEE_USD)}* a tu balance.",
                    parse_mode="Markdown",
                    reply_markup=kb_compete_again()
                )
            except Exception as e:
                logger.error(f"Error reembolso timeout: {e}")
        return

    # Uno reportó, el otro no
    if r1 is not None and r2 is None:
        reporter_id, no_reporter_id = p1_id, p2_id
        outcome = r1["outcome"]
    elif r2 is not None and r1 is None:
        reporter_id, no_reporter_id = p2_id, p1_id
        outcome = r2["outcome"]
    else:
        return  # ambos ya reportaron, el handle_result lo resolvió

    winner_id = reporter_id if outcome == "win" else no_reporter_id
    loser_id  = no_reporter_id if outcome == "win" else reporter_id

    await _finalize_match_auto(
        context.bot, match_id, winner_id, loser_id, data["game_mode"]
    )
    try:
        await context.bot.send_message(
            no_reporter_id,
            f"⏱ *Tiempo agotado — Partida #{match_id}*\n\n"
            f"No reportaste el resultado a tiempo.\n"
            f"La partida fue asignada al oponente.",
            parse_mode="Markdown",
            reply_markup=kb_compete_again()
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
            "⚠️ Esta partida ya fue procesada.",
            reply_markup=kb_compete_again()
        )
        return

    if db.get_match_report(match_id, user.id):
        await update.callback_query.answer(
            "Ya reportaste tu resultado. Esperando al oponente...",
            show_alert=True
        )
        return

    db.set_match_report(match_id, user.id, outcome)

    other_id     = (match["player2_id"] if match["player1_id"] == user.id
                    else match["player1_id"])
    other_report = db.get_match_report(match_id, other_id)

    if other_report is None:
        await update.callback_query.edit_message_text(
            f"✅ Reportaste: *{'🏆 Victoria' if outcome == 'win' else '😞 Derrota'}*\n\n"
            f"Esperando que tu oponente reporte...\n"
            f"⏰ Límite: {RESULT_TIMEOUT_MIN} min desde el inicio de la partida.",
            parse_mode="Markdown"
        )
        return

    other_outcome = other_report["outcome"]

    if (outcome == "win" and other_outcome == "lose") or \
       (outcome == "lose" and other_outcome == "win"):
        winner_id = user.id if outcome == "win" else other_id
        loser_id  = other_id if outcome == "win" else user.id
        _cancel_match_jobs(ctx.application, match_id)
        await _finalize_match_auto(
            update.get_bot(), match_id, winner_id, loser_id, match["game_mode"]
        )
        return

    # Conflicto
    _cancel_match_jobs(ctx.application, match_id)
    await _open_conflict_dispute(
        update.get_bot(), match_id, match,
        user.id, other_id, outcome, other_outcome
    )


async def _finalize_match_auto(bot, match_id, winner_id, loser_id, game_mode):
    db.finalize_match(match_id, winner_id)
    total_credit = WIN_PRIZE_USD + ENTRY_FEE_USD
    db.update_player_balance(
        winner_id, total_credit,
        f"Victoria Partida #{match_id}", "prize", match_id
    )
    winner = db.get_player(winner_id)
    loser  = db.get_player(loser_id)

    await bot.send_message(
        winner_id,
        f"🏆 *¡Victoria en Partida #{match_id}!*\n\n"
        f"💰 Premio neto: *{fmt_usd(WIN_PRIZE_USD)}*\n"
        f"💵 Inscripción recuperada: *{fmt_usd(ENTRY_FEE_USD)}*\n"
        f"✅ *Total: {fmt_usd(total_credit)}*\n\n"
        f"Balance: {fmt_usd(winner['balance_usd'])}",
        parse_mode="Markdown",
        reply_markup=kb_compete_again()
    )
    await bot.send_message(
        loser_id,
        f"😞 *Derrota en Partida #{match_id}*\n\n"
        f"¡Sigue intentando! La próxima es tuya. 💪",
        parse_mode="Markdown",
        reply_markup=kb_compete_again()
    )

    try:
        await bot.send_message(
            chat_id           = GROUP_ID,
            message_thread_id = TOPIC_RESULTS_ID,
            text              = (
                f"🏆 *Resultado — Partida #{match_id}*\n\n"
                f"🥇 Ganador: *{winner['cr_name']}*\n"
                f"😞 Perdedor: {loser['cr_name']}\n"
                f"🎮 {mode_label(game_mode)}"
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"No se pudo publicar resultado: {e}")


async def _open_conflict_dispute(bot, match_id, match, p_id, other_id,
                                   p_outcome, other_outcome):
    reason     = (f"Conflicto: J1 reportó '{p_outcome}', "
                  f"J2 reportó '{other_outcome}'")
    dispute_id = db.create_dispute(match_id, p_id, reason)

    for pid in [p_id, other_id]:
        try:
            # Marcar en user_data que están esperando capture de disputa
            # Se hace vía callback especial
            await bot.send_message(
                pid,
                f"⚠️ *Disputa automática — Partida #{match_id}*\n\n"
                f"Los reportes no coinciden.\n"
                f"📸 Envía tu capture de la pantalla de resultado:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "📸 Enviar mi capture",
                        callback_data=f"submit_dispute_proof_{match_id}"
                    )
                ]])
            )
        except Exception as e:
            logger.error(f"Error notificando disputa: {e}")

    p1 = db.get_player(match["player1_id"])
    p2 = db.get_player(match["player2_id"])
    await notify_admin(
        bot,
        f"⚖️ *Disputa automática #{dispute_id}*\n\n"
        f"Partida #{match_id} | {mode_label(match['game_mode'])}\n"
        f"👤 {p1['cr_name']} vs {p2['cr_name']}\n\n"
        f"Motivo: {reason}",
        reply_markup=kb_dispute_resolve(
            dispute_id, match["player1_id"], match["player2_id"]
        )
    )


# ── Capture de disputa — COMPLETAMENTE SEPARADO del flow de pago ──────────────

async def start_dispute_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """El jugador presiona 'Enviar mi capture' en una disputa."""
    await update.callback_query.answer()
    raw = update.callback_query.data.replace("submit_dispute_proof_", "")
    try:
        match_id = int(raw)
    except ValueError:
        await update.callback_query.answer("Error.", show_alert=True)
        return ConversationHandler.END

    ctx.user_data["dispute_proof_match_id"] = match_id
    await update.callback_query.message.reply_text(
        f"📸 Envía el capture de la *Partida #{match_id}*\n"
        f"_(pantalla de resultado dentro de Clash Royale)_",
        parse_mode="Markdown"
    )
    return WAITING_DISPUTE_PROOF


async def receive_dispute_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Recibe el capture de una DISPUTA.
    Completamente separado del receive_payment_proof.
    """
    user     = update.effective_user
    file_id  = update.message.photo[-1].file_id
    match_id = ctx.user_data.get("dispute_proof_match_id")
    match    = db.get_match(match_id) if match_id else None
    player   = db.get_player(user.id)

    if not match:
        await update.message.reply_text("⚠️ No se encontró la partida de la disputa.")
        return ConversationHandler.END

    db.set_match_result_proof(match_id, user.id, file_id)
    await update.message.reply_text(
        "✅ Capture de disputa recibido.\n"
        "El administrador lo revisará y decidirá el resultado.",
        reply_markup=kb_main_menu()
    )

    from utils import kb_result_review
    await notify_admin(
        update.get_bot(),
        f"⚖️ *Capture de disputa — Partida #{match_id}*\n"
        f"👤 *{player['cr_name']}*\n"
        f"🎮 {mode_label(match['game_mode'])}",
        reply_markup=kb_result_review(match_id, user.id),
        photo=file_id
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
        parse_mode="Markdown",
        reply_markup=kb_main_menu()
    )

    opp_id = (match["player2_id"] if match["player1_id"] == user.id
              else match["player1_id"])
    try:
        await update.get_bot().send_message(
            opp_id,
            f"⚠️ Tu oponente abrió una disputa en Partida #{match_id}."
        )
    except Exception:
        pass

    await notify_admin(
        update.get_bot(),
        f"⚖️ *Disputa #{dispute_id}*\n\n"
        f"Partida #{match_id} | {mode_label(match['game_mode'])}\n"
        f"Por: *{player['cr_name']}*\n\n"
        f"Motivo: {reason}",
        reply_markup=kb_dispute_resolve(
            dispute_id, match["player1_id"], match["player2_id"]
        )
    )
    ctx.user_data.clear()
    return ConversationHandler.END
