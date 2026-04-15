"""
Panel de administración v5
- Notificaciones al canal privado del admin
- Broadcast SOLO al tema Anuncios del grupo
- Torneos funcionales con volver
- Estado de partidas correcto
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import database as db
import services
from utils import (
    kb_admin_main, kb_back_to_admin, kb_main_menu,
    kb_manage_player, kb_payment_review, kb_withdrawal_review,
    kb_dispute_resolve, kb_game_modes, kb_confirm,
    fmt_usd, fmt_ves, fmt_date, mode_label,
)
from config import (
    ADMIN_IDS, GROUP_ID, TOPIC_RESULTS_ID,
    TOPIC_ANNOUNCEMENTS_ID, ADMIN_CHANNEL_ID,
    WIN_PRIZE_USD, ENTRY_FEE_USD,
)

logger = logging.getLogger(__name__)

BROADCAST_MSG, BROADCAST_OK               = range(30, 32)
MANAGE_SEARCH, MANAGE_ACTION, MANAGE_BALANCE = range(32, 35)
TOURN_NAME, TOURN_MODE, TOURN_FEE, TOURN_PRIZE, TOURN_CONFIRM = range(35, 40)
EDIT_TEXT_SELECT, EDIT_TEXT_INPUT         = range(40, 42)
WIN_LIMIT_INPUT                           = 42


def is_admin(uid): return uid in ADMIN_IDS


def admin_only(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if not is_admin(uid):
            if update.callback_query:
                await update.callback_query.answer("⛔ Sin acceso", show_alert=True)
            else:
                await update.message.reply_text("⛔ Acceso denegado.")
            return ConversationHandler.END
        return await func(update, ctx)
    wrapper.__name__ = func.__name__
    return wrapper


# ── /admin ────────────────────────────────────────────────────────────────────

@admin_only
async def cmd_admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = db.get_stats()
    await update.message.reply_text(
        f"🛡 *Panel ArenaX*\n\n"
        f"👥 {s['total_players']} jugadores | "
        f"⚔️ {s['today_matches']} partidas hoy\n"
        f"⏳ {s['queue_count']} en cola | "
        f"⚖️ {s['open_disputes']} disputas",
        parse_mode="Markdown",
        reply_markup=kb_admin_main()
    )


async def back_to_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    ctx.user_data.clear()
    s = db.get_stats()
    await update.callback_query.edit_message_text(
        f"🛡 *Panel ArenaX*\n\n"
        f"👥 {s['total_players']} jugadores | "
        f"⚔️ {s['today_matches']} partidas hoy\n"
        f"⏳ {s['queue_count']} en cola | "
        f"⚖️ {s['open_disputes']} disputas",
        parse_mode="Markdown",
        reply_markup=kb_admin_main()
    )


# ── Pagos ─────────────────────────────────────────────────────────────────────

@admin_only
async def admin_payments(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    payments = db.get_pending_payments()
    if not payments:
        await update.callback_query.edit_message_text(
            "✅ Sin pagos pendientes.", reply_markup=kb_admin_main()
        )
        return
    await update.callback_query.edit_message_text(
        f"💳 *{len(payments)} pagos pendientes:*",
        parse_mode="Markdown", reply_markup=kb_admin_main()
    )
    for p in payments:
        try:
            await update.get_bot().send_photo(
                chat_id      = update.effective_user.id,
                photo        = p["proof_file_id"],
                caption      = (
                    f"💳 *Pago #{p['id']}*\n"
                    f"👤 {p['cr_name']}\n"
                    f"🎮 {mode_label(p['game_mode'])} | "
                    f"💵 {fmt_usd(p['amount_usd'])}\n"
                    f"📅 {fmt_date(p['created_at'])}"
                ),
                parse_mode   = "Markdown",
                reply_markup = kb_payment_review(p["id"])
            )
        except Exception as e:
            logger.error(f"Error mostrando pago {p['id']}: {e}")


@admin_only
async def admin_withdrawals(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    wds = db.get_pending_withdrawals()
    if not wds:
        await update.callback_query.edit_message_text(
            "✅ Sin retiros pendientes.", reply_markup=kb_admin_main()
        )
        return
    await update.callback_query.edit_message_text(
        f"💸 *{len(wds)} retiros pendientes:*",
        parse_mode="Markdown", reply_markup=kb_admin_main()
    )
    for wd in wds:
        try:
            await update.get_bot().send_message(
                chat_id      = update.effective_user.id,
                text         = (
                    f"💸 *Retiro #{wd['id']}*\n"
                    f"👤 {wd['cr_name']}\n"
                    f"💵 {fmt_usd(wd['amount_usd'])} = {fmt_ves(wd['amount_ves'])}\n"
                    f"🏦 {wd['bank_name']} | 📱 {wd['phone']}\n"
                    f"🪪 {wd['cedula']}"
                ),
                parse_mode   = "Markdown",
                reply_markup = kb_withdrawal_review(wd["id"])
            )
        except Exception as e:
            logger.error(f"Error mostrando retiro {wd['id']}: {e}")


@admin_only
async def approve_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("✅ Aprobando...")
    pay_id = int(update.callback_query.data.replace("pay_approve_", ""))
    pay    = db.get_payment(pay_id)
    if not pay or pay["status"] != "pending":
        await update.callback_query.answer("⚠️ Ya procesado", show_alert=True)
        return
    db.update_payment_status(pay_id, "approved", update.effective_user.id)
    await update.callback_query.edit_message_caption(
        (update.callback_query.message.caption or "") + "\n\n✅ *APROBADO*",
        parse_mode="Markdown"
    )
    await update.get_bot().send_message(
        pay["telegram_id"],
        f"✅ *Pago aprobado.* Entrando en cola para {mode_label(pay['game_mode'])}... ⏳",
        parse_mode="Markdown"
    )
    from handlers.competition import try_match
    await try_match(update.get_bot(), pay["telegram_id"], pay["game_mode"], pay_id)


@admin_only
async def reject_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("❌ Rechazando...")
    pay_id = int(update.callback_query.data.replace("pay_reject_", ""))
    pay    = db.get_payment(pay_id)
    if not pay or pay["status"] != "pending":
        await update.callback_query.answer("⚠️ Ya procesado", show_alert=True)
        return
    db.update_payment_status(pay_id, "rejected", update.effective_user.id)
    await update.callback_query.edit_message_caption(
        (update.callback_query.message.caption or "") + "\n\n❌ *RECHAZADO*",
        parse_mode="Markdown"
    )
    await update.get_bot().send_message(
        pay["telegram_id"],
        "❌ *Tu pago fue rechazado.* Contacta al administrador si crees que es un error.",
        parse_mode="Markdown"
    )


@admin_only
async def approve_withdraw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    wd_id = int(update.callback_query.data.replace("wd_approve_", ""))
    db.update_withdrawal_status(wd_id, "approved")
    wd = db.get_withdrawal(wd_id)
    await update.callback_query.edit_message_text(
        update.callback_query.message.text + "\n\n✅ *PAGO ENVIADO*",
        parse_mode="Markdown"
    )
    await update.get_bot().send_message(
        wd["telegram_id"],
        f"✅ *Retiro procesado.* Recibirás {fmt_usd(wd['amount_usd'])} en tu pago móvil. 🎉",
        parse_mode="Markdown"
    )


@admin_only
async def reject_withdraw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    wd_id = int(update.callback_query.data.replace("wd_reject_", ""))
    db.update_withdrawal_status(wd_id, "rejected")
    wd = db.get_withdrawal(wd_id)
    await update.callback_query.edit_message_text(
        update.callback_query.message.text + "\n\n❌ *RECHAZADO — saldo devuelto*",
        parse_mode="Markdown"
    )
    await update.get_bot().send_message(
        wd["telegram_id"],
        f"❌ Retiro rechazado. Se devolvieron {fmt_usd(wd['amount_usd'])} a tu balance.",
        parse_mode="Markdown"
    )


# ── Resultados ────────────────────────────────────────────────────────────────

@admin_only
async def approve_result(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    parts    = update.callback_query.data.replace("res_approve_", "").split("_")
    match_id = int(parts[0])
    winner_id= int(parts[1])
    match    = db.get_match(match_id)
    if not match or match["status"] not in ("active", "disputed"):
        await update.callback_query.answer("⚠️ Partida ya procesada", show_alert=True)
        return

    from handlers.competition import _finalize_match_auto
    loser_id = match["player2_id"] if match["player1_id"] == winner_id else match["player1_id"]
    await _finalize_match_auto(
        update.get_bot(), match_id, winner_id, loser_id, match["game_mode"]
    )
    await update.callback_query.edit_message_caption(
        (update.callback_query.message.caption or "") +
        f"\n\n✅ *Victoria confirmada*",
        parse_mode="Markdown"
    )


@admin_only
async def reject_result(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    parts    = update.callback_query.data.replace("res_reject_", "").split("_")
    match_id = int(parts[0])
    # Marcar partida como disputada para revisión
    db.update_match_status(match_id, "disputed")
    await update.callback_query.edit_message_caption(
        (update.callback_query.message.caption or "") +
        "\n\n⚠️ *Resultado rechazado — en disputa*",
        parse_mode="Markdown"
    )
    match = db.get_match(match_id)
    for pid in [match["player1_id"], match["player2_id"]]:
        try:
            await update.get_bot().send_message(
                pid,
                f"⚠️ El resultado de la Partida #{match_id} fue rechazado. "
                "El administrador revisará la situación.",
                parse_mode="Markdown"
            )
        except Exception:
            pass


# ── Disputas ──────────────────────────────────────────────────────────────────

@admin_only
async def admin_disputes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    disputes = db.get_open_disputes()
    if not disputes:
        await update.callback_query.edit_message_text(
            "✅ No hay disputas abiertas.", reply_markup=kb_admin_main()
        )
        return
    await update.callback_query.edit_message_text(
        f"⚖️ *{len(disputes)} disputas abiertas:*",
        parse_mode="Markdown", reply_markup=kb_admin_main()
    )
    for d in disputes:
        match = db.get_match(d["match_id"])
        try:
            await update.get_bot().send_message(
                update.effective_user.id,
                f"⚖️ *Disputa #{d['id']}*\n"
                f"Partida #{d['match_id']} | {mode_label(d['game_mode'])}\n"
                f"Reportado por: *{d['reporter_name']}*\n\n"
                f"Motivo: {d['reason'] or 'Sin descripción'}",
                parse_mode="Markdown",
                reply_markup=kb_dispute_resolve(
                    d["id"], match["player1_id"], match["player2_id"]
                )
            )
        except Exception as e:
            logger.error(f"Error mostrando disputa: {e}")


@admin_only
async def resolve_dispute(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    parts      = update.callback_query.data.split("_")
    action     = parts[1]
    dispute_id = int(parts[2])
    winner_raw = int(parts[3])

    disputes = db.get_open_disputes()
    dispute  = next((d for d in disputes if d["id"] == dispute_id), None)
    if not dispute:
        await update.callback_query.answer("⚠️ Disputa no encontrada", show_alert=True)
        return

    match = db.get_match(dispute["match_id"])

    if action == "void":
        for pid in [match["player1_id"], match["player2_id"]]:
            db.update_player_balance(
                pid, ENTRY_FEE_USD,
                f"Reembolso partida #{match['id']} anulada", "refund"
            )
            try:
                await update.get_bot().send_message(
                    pid,
                    f"⚖️ Partida #{match['id']} anulada. "
                    f"Se te devolvió {fmt_usd(ENTRY_FEE_USD)}.",
                    parse_mode="Markdown",
                    reply_markup=kb_main_menu()
                )
            except Exception:
                pass
        db.resolve_dispute(dispute_id, None, "Anulada — reembolso a ambos")
        await update.callback_query.edit_message_text("❌ Partida anulada. Reembolsos enviados.")
    else:
        winner_id = winner_raw
        winner    = db.get_player(winner_id)
        loser_id  = match["player2_id"] if match["player1_id"] == winner_id else match["player1_id"]

        from handlers.competition import _finalize_match_auto
        await _finalize_match_auto(
            update.get_bot(), dispute["match_id"],
            winner_id, loser_id, match["game_mode"]
        )
        db.resolve_dispute(dispute_id, winner_id, f"Victoria a {winner['cr_name']}")
        await update.callback_query.edit_message_text(
            f"✅ Disputa resuelta. Victoria a *{winner['cr_name']}*",
            parse_mode="Markdown"
        )


# ── Cola ──────────────────────────────────────────────────────────────────────

@admin_only
async def admin_queue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    queue = db.get_queue()
    if not queue:
        await update.callback_query.edit_message_text(
            "⏳ Cola vacía.", reply_markup=kb_admin_main()
        )
        return
    lines = [f"⏳ *Cola ({len(queue)} jugadores):*\n"]
    for i, q in enumerate(queue, 1):
        lines.append(
            f"{i}. *{q['cr_name']}* — {mode_label(q['game_mode'])} — {fmt_date(q['entered_at'])}"
        )
    await update.callback_query.edit_message_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=kb_admin_main()
    )


@admin_only
async def remove_from_queue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = int(update.callback_query.data.replace("queue_remove_", ""))
    db.remove_from_queue(tid)
    try:
        await update.get_bot().send_message(
            tid, "ℹ️ Fuiste removido de la cola por el administrador."
        )
    except Exception:
        pass
    await update.callback_query.answer("✅ Removido", show_alert=True)


# ── Partidas ──────────────────────────────────────────────────────────────────

@admin_only
async def admin_matches(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    matches = db.get_all_matches(limit=25)
    if not matches:
        await update.callback_query.edit_message_text(
            "⚔️ Sin partidas.", reply_markup=kb_admin_main()
        )
        return
    icons = {"active": "🟡", "completed": "✅", "disputed": "⚠️", "voided": "❌"}
    lines = ["⚔️ *Partidas recientes:*\n"]
    for m in matches:
        w = m["winner_name"] or "En curso"
        lines.append(
            f"{icons.get(m['status'], '❓')} "
            f"*#{m['id']}* {m['p1_name']} vs {m['p2_name']} — {w}"
        )
    await update.callback_query.edit_message_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=kb_admin_main()
    )


# ── Finanzas ──────────────────────────────────────────────────────────────────

@admin_only
async def admin_finances(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    fin  = db.get_finance_summary()
    rate = await services.get_bcv_rate()
    await update.callback_query.edit_message_text(
        f"💰 *Finanzas ArenaX*\n\n"
        f"📈 Tasa BCV: {services.format_rate(rate)}\n\n"
        f"✅ Total inscripciones: {fmt_usd(fin['total_in'])}\n"
        f"💸 Total retirado:      {fmt_usd(fin['total_out'])}\n"
        f"💰 Saldo jugadores:     {fmt_usd(fin['total_player_balance'])}\n\n"
        f"⏳ Pagos pendientes:   {fin['pending_payments']}\n"
        f"⏳ Retiros pendientes: {fin['pending_withdrawals']}",
        parse_mode="Markdown", reply_markup=kb_admin_main()
    )


# ── Jugadores ─────────────────────────────────────────────────────────────────

@admin_only
async def admin_players(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    players = db.get_all_players()
    icons   = {"active": "🟢", "suspended": "🟡", "banned": "🔴"}
    lines   = [f"👥 *Jugadores ({len(players)}):*\n"]
    for p in players[:30]:
        lines.append(
            f"{icons.get(p['status'], '⚪')} *{p['cr_name']}* "
            f"`{p['cr_tag']}` — {fmt_usd(p['balance_usd'])}"
        )
    await update.callback_query.edit_message_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=kb_admin_main()
    )


@admin_only
async def manage_player_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "🔍 Ingresa el *tag CR* del jugador:",
        parse_mode="Markdown"
    )
    return MANAGE_SEARCH


async def manage_player_found(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tag    = services.normalize_tag(update.message.text.strip())
    player = db.get_player_by_tag(tag)
    if not player:
        await update.message.reply_text(f"❌ Jugador `{tag}` no encontrado.", parse_mode="Markdown")
        return MANAGE_SEARCH
    ctx.user_data["manage_player_id"] = player["telegram_id"]
    icons = {"active": "🟢 Activo", "suspended": "🟡 Suspendido", "banned": "🔴 Baneado"}
    await update.message.reply_text(
        f"👤 *{player['cr_name']}* (`{player['cr_tag']}`)\n"
        f"💰 {fmt_usd(player['balance_usd'])} | 🎯 {player['total_matches']} partidas\n"
        f"📊 {icons.get(player['status'], player['status'])}",
        parse_mode="Markdown",
        reply_markup=kb_manage_player(player["telegram_id"])
    )
    return MANAGE_ACTION


async def manage_player_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    data = update.callback_query.data
    tid  = ctx.user_data.get("manage_player_id")

    if "add" in data or "sub" in data:
        ctx.user_data["balance_action"] = "add" if "add" in data else "sub"
        await update.callback_query.edit_message_text(
            f"💵 ¿Cuánto USD deseas {'añadir' if 'add' in data else 'quitar'}?"
        )
        return MANAGE_BALANCE

    actions = {
        "suspend":  ("suspended", "🚫 Suspendido.", "🚫 Tu cuenta fue suspendida."),
        "activate": ("active",    "✅ Reactivado.", "✅ Tu cuenta fue reactivada."),
        "ban":      ("banned",    "⛔ Baneado.",    None),
    }
    for key, (status, admin_msg, user_msg) in actions.items():
        if key in data:
            db.set_player_status(tid, status)
            await update.callback_query.edit_message_text(admin_msg)
            if user_msg:
                try: await update.get_bot().send_message(tid, user_msg)
                except Exception: pass
            ctx.user_data.clear()
            return ConversationHandler.END

    if "dequeue" in data:
        db.remove_from_queue(tid)
        await update.callback_query.edit_message_text("🗑 Removido de la cola.")
        try: await update.get_bot().send_message(tid, "ℹ️ Fuiste removido de la cola.")
        except Exception: pass
        ctx.user_data.clear()
        return ConversationHandler.END

    return MANAGE_ACTION


async def manage_balance_apply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip().replace(",", ".").replace("$", ""))
    except ValueError:
        await update.message.reply_text("⚠️ Monto inválido.")
        return MANAGE_BALANCE

    tid    = ctx.user_data.get("manage_player_id")
    action = ctx.user_data.get("balance_action", "add")
    delta  = amount if action == "add" else -amount
    db.update_player_balance(tid, delta, "Ajuste manual admin", "admin_adjustment")
    player = db.get_player(tid)
    await update.message.reply_text(
        f"✅ Listo. Balance de *{player['cr_name']}*: {fmt_usd(player['balance_usd'])}",
        parse_mode="Markdown"
    )
    try:
        await update.get_bot().send_message(
            tid,
            f"💰 El admin {'añadió' if delta > 0 else 'dedujo'} "
            f"{fmt_usd(abs(delta))}.\n"
            f"Balance: {fmt_usd(player['balance_usd'])}",
            parse_mode="Markdown"
        )
    except Exception: pass
    ctx.user_data.clear()
    return ConversationHandler.END


# ── Estadísticas ──────────────────────────────────────────────────────────────

@admin_only
async def admin_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    s   = db.get_stats()
    fin = db.get_finance_summary()
    rate= await services.get_bcv_rate()
    await update.callback_query.edit_message_text(
        f"📊 *Estadísticas ArenaX*\n\n"
        f"👥 Jugadores: {s['total_players']} ({s['active_players']} activos)\n"
        f"⚔️ Partidas: {s['total_matches']} total | {s['today_matches']} hoy\n"
        f"⏳ En cola: {s['queue_count']} | ⚖️ Disputas: {s['open_disputes']}\n\n"
        f"💵 Inscripciones: {fmt_usd(fin['total_in'])}\n"
        f"💸 Retirado:      {fmt_usd(fin['total_out'])}\n"
        f"📈 Tasa BCV:      {services.format_rate(rate)}",
        parse_mode="Markdown", reply_markup=kb_admin_main()
    )


# ── Torneos ───────────────────────────────────────────────────────────────────

@admin_only
async def admin_tournaments(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    ts = db.get_active_tournaments()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Crear torneo", callback_data="admin_tournament_create")],
        [InlineKeyboardButton("🔙 Volver",       callback_data="admin_back")],
    ])
    lines = ["🏆 *Torneos:*\n"]
    if not ts:
        lines.append("_No hay torneos activos._")
    for t in ts:
        lines.append(
            f"{'🟢' if t['status']=='active' else '🟡'} *{t['name']}*\n"
            f"   🎮 {mode_label(t['game_mode'])} | "
            f"💳 {fmt_usd(t['entry_fee'])} | 🏆 {fmt_usd(t['prize_usd'])}"
        )
    await update.callback_query.edit_message_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=kb
    )


@admin_only
async def create_tournament_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    ctx.user_data.clear()
    await update.callback_query.edit_message_text(
        "🏆 *Crear torneo — 1/4*\n\n¿Nombre del torneo?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancelar", callback_data="admin_back")]
        ])
    )
    return TOURN_NAME


async def tourn_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["tourn_name"] = update.message.text.strip()
    await update.message.reply_text(
        "🎮 *2/4 — Modo de juego:*",
        parse_mode="Markdown",
        reply_markup=kb_game_modes(back_data="admin_back")
    )
    return TOURN_MODE


async def tourn_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    ctx.user_data["tourn_mode"] = update.callback_query.data.replace("mode_", "")
    await update.callback_query.edit_message_text(
        "💳 *3/4 — Inscripción por jugador (USD):*\nEjemplo: `2.00`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Volver", callback_data="admin_back")]
        ])
    )
    return TOURN_FEE


async def tourn_fee(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["tourn_fee"] = float(update.message.text.strip().replace(",", "."))
    except ValueError:
        await update.message.reply_text("⚠️ Monto inválido. Ejemplo: `2.00`", parse_mode="Markdown")
        return TOURN_FEE
    await update.message.reply_text(
        "🏆 *4/4 — Premio al ganador (USD):*\nEjemplo: `15.00`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Volver", callback_data="admin_back")]
        ])
    )
    return TOURN_PRIZE


async def tourn_prize(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["tourn_prize"] = float(update.message.text.strip().replace(",", "."))
    except ValueError:
        await update.message.reply_text("⚠️ Monto inválido.")
        return TOURN_PRIZE

    ud = ctx.user_data
    await update.message.reply_text(
        f"📋 *Confirmar torneo*\n\n"
        f"🏆 *{ud['tourn_name']}*\n"
        f"🎮 {mode_label(ud['tourn_mode'])}\n"
        f"💳 Inscripción: {fmt_usd(ud['tourn_fee'])}\n"
        f"🥇 Premio: {fmt_usd(ud['tourn_prize'])}\n\n"
        f"¿Confirmas?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Crear", callback_data="tourn_ok"),
             InlineKeyboardButton("❌ Cancelar", callback_data="tourn_cancel")],
        ])
    )
    return TOURN_CONFIRM


async def tourn_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    if update.callback_query.data == "tourn_cancel":
        ctx.user_data.clear()
        await update.callback_query.edit_message_text("❌ Torneo cancelado.")
        return ConversationHandler.END

    ud   = ctx.user_data
    t_id = db.create_tournament(
        ud["tourn_name"], ud["tourn_mode"],
        ud["tourn_prize"], 3, None, ud["tourn_fee"]
    )
    await update.callback_query.edit_message_text(
        f"✅ *Torneo #{t_id} creado.*",
        parse_mode="Markdown", reply_markup=kb_admin_main()
    )

    # Anunciar en el tema Anuncios del grupo
    try:
        await update.get_bot().send_message(
            chat_id           = GROUP_ID,
            message_thread_id = TOPIC_ANNOUNCEMENTS_ID,
            text              = (
                f"🏆 *¡Nuevo torneo ArenaX!*\n\n"
                f"📛 *{ud['tourn_name']}*\n"
                f"🎮 {mode_label(ud['tourn_mode'])}\n"
                f"💳 Inscripción: {fmt_usd(ud['tourn_fee'])}\n"
                f"🥇 Premio: {fmt_usd(ud['tourn_prize'])}\n\n"
                f"¡Prepárate! 🔥"
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"No se pudo anunciar torneo: {e}")

    ctx.user_data.clear()
    return ConversationHandler.END


# ── Broadcast — SOLO al tema Anuncios del grupo ───────────────────────────────

@admin_only
async def broadcast_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "📢 *Broadcast al grupo oficial*\n\n"
        "El mensaje se enviará al tema *Anuncios* del grupo.\n\n"
        "Escribe el mensaje:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancelar", callback_data="admin_back")]
        ])
    )
    return BROADCAST_MSG


async def broadcast_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["broadcast_text"] = update.message.text
    await update.message.reply_text(
        f"¿Confirmas publicar este mensaje en el grupo?\n\n"
        f"─────\n{update.message.text}\n─────",
        reply_markup=kb_confirm(
            "broadcast_yes", "broadcast_no",
            "📢 Publicar en grupo", "❌ Cancelar"
        )
    )
    return BROADCAST_OK


async def broadcast_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    if update.callback_query.data == "broadcast_no":
        ctx.user_data.clear()
        await update.callback_query.edit_message_text("❌ Broadcast cancelado.")
        return ConversationHandler.END

    msg = ctx.user_data.get("broadcast_text", "")

    # SOLO al tema Anuncios del grupo oficial
    try:
        await update.get_bot().send_message(
            chat_id           = GROUP_ID,
            message_thread_id = TOPIC_ANNOUNCEMENTS_ID,
            text              = f"📢 *Anuncio ArenaX:*\n\n{msg}",
            parse_mode        = "Markdown"
        )
        await update.callback_query.edit_message_text(
            "✅ *Anuncio publicado* en el tema Anuncios del grupo.",
            parse_mode="Markdown", reply_markup=kb_admin_main()
        )
    except Exception as e:
        await update.callback_query.edit_message_text(
            f"❌ Error al publicar: `{e}`\n\n"
            "Verifica que el bot sea admin del grupo y el ID del tema sea correcto.",
            parse_mode="Markdown", reply_markup=kb_admin_main()
        )

    ctx.user_data.clear()
    return ConversationHandler.END


# ── Editar textos ─────────────────────────────────────────────────────────────

@admin_only
async def edit_texts_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👋 Bienvenida",             callback_data="text_welcome")],
        [InlineKeyboardButton("📋 Términos y condiciones", callback_data="text_terms")],
        [InlineKeyboardButton("💳 Instrucciones de pago",  callback_data="text_payment_instructions")],
        [InlineKeyboardButton("⚔️ Reglas de partida",      callback_data="text_match_rules")],
        [InlineKeyboardButton("🔙 Volver",                 callback_data="admin_back")],
    ])
    await update.callback_query.edit_message_text(
        "📝 *Editar textos* — ¿Qué deseas editar?",
        parse_mode="Markdown", reply_markup=kb
    )
    return EDIT_TEXT_SELECT


async def edit_text_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    key = update.callback_query.data.replace("text_", "")
    ctx.user_data["edit_text_key"] = key
    current = db.get_text(key)
    await update.callback_query.edit_message_text(
        f"📝 Texto actual:\n\n`{current[:500]}`\n\n"
        "Envía el nuevo texto (Markdown soportado):",
        parse_mode="Markdown"
    )
    return EDIT_TEXT_INPUT


async def edit_text_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    key = ctx.user_data.get("edit_text_key")
    db.set_text(key, update.message.text)
    ctx.user_data.clear()
    await update.message.reply_text(
        "✅ Texto actualizado.", reply_markup=kb_admin_main()
    )
    return ConversationHandler.END


# ── Límite victorias ──────────────────────────────────────────────────────────

@admin_only
async def admin_win_limit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    current = db.get_setting("win_limit_day")
    await update.callback_query.edit_message_text(
        f"🔢 *Límite victorias/día*\n\nActual: *{current}*\n\n"
        "Envía el nuevo número:",
        parse_mode="Markdown",
        reply_markup=kb_back_to_admin()
    )


# ── Sync Sheets ───────────────────────────────────────────────────────────────

@admin_only
async def admin_sync_sheets(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("🔄 Sincronizando con Google Sheets...")
    result = services.sync_to_sheets()
    if result["ok"]:
        await update.callback_query.edit_message_text(
            f"✅ *Sync completado*\n"
            f"👥 {result['players']} jugadores | ⚔️ {result['matches']} partidas",
            parse_mode="Markdown", reply_markup=kb_admin_main()
        )
    else:
        await update.callback_query.edit_message_text(
            f"❌ *Error en sync:*\n`{result.get('error', 'desconocido')}`\n\n"
            "Verifica `GOOGLE_CREDENTIALS_JSON` en Railway.",
            parse_mode="Markdown", reply_markup=kb_admin_main()
        )


@admin_only
async def cmd_sync_sheets(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Sincronizando...")
    r = services.sync_to_sheets()
    if r["ok"]:
        await msg.edit_text(f"✅ {r['players']} jugadores, {r['matches']} partidas sincronizados.")
    else:
        await msg.edit_text(f"❌ Error: {r.get('error', 'sin credenciales')}")
