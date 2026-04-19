"""
Perfil v7:
- Editar pago móvil: flujo independiente (tel→ced→banco), sin link de amistad
- Editar link de amistad: flujo independiente
- Botón volver en todos los pasos
- Efecto desvanecimiento
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import database as db
import services
from utils import (kb_main_menu, kb_banks, kb_back_to_menu, kb_profile_options,
                   kb_confirm, fmt_usd, fmt_ves, fmt_date, fmt_pct, mode_label,
                   is_business_hours)
from config import ADMIN_IDS, BANKS as BANKS_CONFIG, MIN_WITHDRAW_USD, ADMIN_CHANNEL_ID

logger = logging.getLogger(__name__)

EDIT_PHONE, EDIT_CEDULA, EDIT_BANK = range(20, 23)
EDIT_FRIEND                         = 23
WITHDRAW_AMOUNT, WITHDRAW_CONFIRM   = range(24, 26)


async def _notify_admin(bot, text, reply_markup=None):
    target = ADMIN_CHANNEL_ID if ADMIN_CHANNEL_ID != 0 else ADMIN_IDS[0]
    try:
        await bot.send_message(chat_id=target, text=text,
                                parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error admin: {e}")
        if target != ADMIN_IDS[0]:
            try:
                await bot.send_message(chat_id=ADMIN_IDS[0], text=text,
                                        parse_mode="Markdown", reply_markup=reply_markup)
            except Exception:
                pass


def _back_profile():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Volver al perfil", callback_data="menu_profile")]
    ])


async def show_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user   = update.effective_user
    player = db.get_player(user.id)
    if not player:
        await update.callback_query.message.reply_text("⚠️ No tienes cuenta. Usa /start")
        return
    total  = player["total_matches"]
    wins   = player["total_wins"]
    losses = player["total_losses"]
    pct    = fmt_pct(wins, total)
    icons  = {"active": "🟢 Activo", "suspended": "🟡 Suspendido", "banned": "🔴 Baneado"}
    await update.callback_query.edit_message_text(
        f"👤 *Tu perfil — ArenaX*\n\n"
        f"🎮 *Tag CR:* `{player['cr_tag']}`\n"
        f"📛 *Nombre:* {player['cr_name']}\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📱 *Teléfono:* {player['phone']}\n"
        f"🪪 *Cédula:* {player['cedula']}\n"
        f"🏦 *Banco:* {player['bank_name']}\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🎯 Partidas jugadas: {total}\n"
        f"🏆 V hoy: {player['wins_today']} | 😞 D hoy: {player['losses_today']}\n"
        f"📈 Total V: {wins} | D: {losses} | {pct}\n"
        f"🔥 Racha: {player['streak_current']} | Mejor: {player['streak_best']}\n\n"
        f"💰 *Balance:* {fmt_usd(player['balance_usd'])}\n"
        f"📊 {icons.get(player['status'], player['status'])}\n"
        f"📅 Registro: {fmt_date(player['registered_at'])}",
        parse_mode="Markdown",
        reply_markup=kb_profile_options()
    )


async def show_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user   = update.effective_user
    player = db.get_player(user.id)
    txs    = db.get_transactions(user.id, limit=15)
    lines  = [f"💰 *Balance: {fmt_usd(player['balance_usd'])}*\n\n📋 *Últimos movimientos:*\n"]
    if not txs:
        lines.append("_Sin movimientos aún._")
    else:
        for tx in txs:
            sign  = "+" if tx["amount_usd"] >= 0 else ""
            emoji = "🟢" if tx["amount_usd"] >= 0 else "🔴"
            lines.append(f"{emoji} {sign}{fmt_usd(tx['amount_usd'])} — "
                         f"{tx['description'] or tx['type']} | {fmt_date(tx['created_at'])}")
    await update.callback_query.edit_message_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=kb_back_to_menu()
    )


async def show_ranking(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    ranking = db.get_daily_ranking()
    if not ranking:
        await update.callback_query.edit_message_text(
            "📊 *Ranking del día*\n\n_Aún no hay partidas hoy._",
            parse_mode="Markdown", reply_markup=kb_back_to_menu()
        )
        return
    medals = ["🥇", "🥈", "🥉"]
    lines  = ["🏆 *Ranking del día — ArenaX*\n"]
    for i, p in enumerate(ranking):
        medal = medals[i] if i < 3 else f"{i+1}."
        pct   = fmt_pct(p["wins_today"], p["wins_today"] + p["losses_today"])
        streak = f" 🔥×{p['streak_current']}" if p["streak_current"] > 1 else ""
        lines.append(f"{medal} *{p['cr_name']}* — {p['wins_today']}V {p['losses_today']}D ({pct}){streak}")
    await update.callback_query.edit_message_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=kb_back_to_menu()
    )


async def show_tournaments(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    tournaments = db.get_active_tournaments()
    if not tournaments:
        await update.callback_query.edit_message_text(
            "🏆 *Torneos activos*\n\n_No hay torneos activos ahora mismo._\n¡Estate atento! 📢",
            parse_mode="Markdown", reply_markup=kb_back_to_menu()
        )
        return
    lines = ["🏆 *Torneos activos — ArenaX*\n"]
    for t in tournaments:
        icon = "🟢" if t["status"] == "active" else "🟡"
        lines.append(f"{icon} *{t['name']}*\n   🎮 {mode_label(t['game_mode'])}\n"
                     f"   💳 {fmt_usd(t['entry_fee'])} | 🏆 {fmt_usd(t['prize_usd'])}\n"
                     f"   📅 {t['start_date'] or 'Por confirmar'}\n")
    await update.callback_query.edit_message_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=kb_back_to_menu()
    )


# ── Editar pago móvil (sin link de amistad) ───────────────────────────────────

async def start_edit_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "📱 *Editar pago móvil — 1/3*\n\nIngresa tu nuevo *número de teléfono*:\nEj: `0412-1234567`",
        parse_mode="Markdown", reply_markup=_back_profile()
    )
    return EDIT_PHONE


async def edit_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    digits = "".join(filter(str.isdigit, update.message.text))
    if len(digits) < 10:
        await update.message.reply_text(
            "⚠️ Número inválido. Ej: `0412-1234567`\nIntenta de nuevo:",
            parse_mode="Markdown", reply_markup=_back_profile()
        )
        return EDIT_PHONE
    ctx.user_data["edit_phone"] = update.message.text.strip()
    await update.message.reply_text(
        "🪪 *Editar pago móvil — 2/3*\n\nIngresa tu nueva *cédula*:\nEj: `V-12345678`",
        parse_mode="Markdown", reply_markup=_back_profile()
    )
    return EDIT_CEDULA


async def edit_cedula(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().upper()
    if not raw.startswith("V-") and not raw.startswith("E-"):
        raw = "V-" + "".join(filter(str.isdigit, raw))
    ctx.user_data["edit_cedula"] = raw
    await update.message.reply_text(
        "🏦 *Editar pago móvil — 3/3*\n\nSelecciona tu *banco*:",
        parse_mode="Markdown", reply_markup=kb_banks(cancel_data="menu_profile")
    )
    return EDIT_BANK


async def edit_bank(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    code      = update.callback_query.data.replace("bank_", "")
    bank_name = next((name for c, name in BANKS_CONFIG if c == code), "Banco")
    user      = update.effective_user
    ud        = ctx.user_data
    db.update_player_payment_data(user.id, ud["edit_phone"], ud["edit_cedula"], code, bank_name)
    ctx.user_data.clear()
    await update.callback_query.edit_message_text(
        f"✅ *Datos de pago actualizados.*\n\n"
        f"📱 {ud['edit_phone']}\n🪪 {ud['edit_cedula']}\n🏦 {bank_name}",
        parse_mode="Markdown", reply_markup=kb_profile_options()
    )
    return ConversationHandler.END


# ── Editar link de amistad ────────────────────────────────────────────────────

async def start_edit_friend(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "🔗 *Editar link de amistad*\n\n"
        "Cópialo desde tu perfil en Clash Royale:\n"
        "_Perfil → ··· → Compartir → Copiar link_\n\n"
        "Envía el nuevo link:",
        parse_mode="Markdown", reply_markup=_back_profile()
    )
    return EDIT_FRIEND


async def edit_friend_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    valid = ("clashroyale" in link.lower() or "supercell" in link.lower()
             or link.startswith("https://") or link.startswith("http://"))
    if not valid:
        await update.message.reply_text(
            "⚠️ Link no válido. Ej: `https://link.clashroyale.com/invite/friend/...`\n\nIntenta de nuevo:",
            parse_mode="Markdown", reply_markup=_back_profile()
        )
        return EDIT_FRIEND
    db.update_player_friend_link(update.effective_user.id, link)
    ctx.user_data.clear()
    await update.message.reply_text(
        "✅ *Link de amistad actualizado.*",
        parse_mode="Markdown", reply_markup=kb_profile_options()
    )
    return ConversationHandler.END


# ── Retiro ────────────────────────────────────────────────────────────────────

async def start_withdraw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user   = update.effective_user
    player = db.get_player(user.id)
    if not is_business_hours():
        await update.callback_query.edit_message_text(
            "🕙 Los retiros solo se procesan de *10am a 10pm* (hora Venezuela).",
            parse_mode="Markdown", reply_markup=kb_back_to_menu()
        )
        return ConversationHandler.END
    balance = player["balance_usd"]
    if balance < MIN_WITHDRAW_USD:
        await update.callback_query.edit_message_text(
            f"💰 Balance: {fmt_usd(balance)}\n\nMínimo de retiro: *{fmt_usd(MIN_WITHDRAW_USD)}*.",
            parse_mode="Markdown", reply_markup=kb_back_to_menu()
        )
        return ConversationHandler.END
    rate = await services.get_bcv_rate()
    ctx.user_data["wd_rate"]    = rate
    ctx.user_data["wd_balance"] = balance
    await update.callback_query.edit_message_text(
        f"💸 *Solicitud de retiro*\n\n"
        f"💰 Balance: *{fmt_usd(balance)}*\n"
        f"📈 Tasa BCV: {services.format_rate(rate)}\n"
        f"🔸 Mínimo: {fmt_usd(MIN_WITHDRAW_USD)}\n\n"
        f"¿Cuánto deseas retirar en USD?",
        parse_mode="Markdown", reply_markup=kb_back_to_menu()
    )
    return WITHDRAW_AMOUNT


async def confirm_withdraw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip().replace(",", ".").replace("$", ""))
    except ValueError:
        await update.message.reply_text("⚠️ Monto inválido. Ejemplo: `3.00`", parse_mode="Markdown")
        return WITHDRAW_AMOUNT
    balance = ctx.user_data.get("wd_balance", 0)
    rate    = ctx.user_data.get("wd_rate", 0)
    if amount < MIN_WITHDRAW_USD:
        await update.message.reply_text(f"⚠️ Mínimo: {fmt_usd(MIN_WITHDRAW_USD)}")
        return WITHDRAW_AMOUNT
    if amount > balance:
        await update.message.reply_text(f"⚠️ Saldo insuficiente. Balance: {fmt_usd(balance)}")
        return WITHDRAW_AMOUNT
    ves = services.usd_to_ves(amount, rate)
    ctx.user_data["wd_amount"] = amount
    ctx.user_data["wd_ves"]    = ves
    player = db.get_player(update.effective_user.id)
    await update.message.reply_text(
        f"📋 *Confirmar retiro*\n\n"
        f"💵 {fmt_usd(amount)} = *{fmt_ves(ves)}*\n"
        f"📈 Tasa: {services.format_rate(rate)}\n\n"
        f"📱 Recibirás en:\n"
        f"   🏦 {player['bank_name']}\n"
        f"   📱 {player['phone']}\n"
        f"   🪪 {player['cedula']}\n\n¿Confirmas?",
        parse_mode="Markdown", reply_markup=kb_confirm("withdraw_ok", "withdraw_no")
    )
    return WITHDRAW_CONFIRM


async def execute_withdraw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    if update.callback_query.data == "withdraw_no":
        ctx.user_data.clear()
        await update.callback_query.edit_message_text("❌ Retiro cancelado.", reply_markup=kb_back_to_menu())
        return ConversationHandler.END
    user   = update.effective_user
    player = db.get_player(user.id)
    ud     = ctx.user_data
    amount, ves, rate = ud["wd_amount"], ud["wd_ves"], ud["wd_rate"]
    wd_id = db.create_withdrawal(user.id, amount, ves, rate,
                                  player["phone"], player["bank_name"], player["cedula"])
    await update.callback_query.edit_message_text(
        f"✅ *Solicitud #{wd_id} enviada.*\nEl administrador procesará tu retiro en breve.",
        parse_mode="Markdown", reply_markup=kb_back_to_menu()
    )
    from utils import kb_withdrawal_review
    await _notify_admin(
        update.get_bot(),
        f"💸 *Retiro pendiente #{wd_id}*\n\n"
        f"👤 {player['cr_name']}\n"
        f"💵 {fmt_usd(amount)} = {fmt_ves(ves)}\n"
        f"🏦 {player['bank_name']} | 📱 {player['phone']}\n🪪 {player['cedula']}",
        reply_markup=kb_withdrawal_review(wd_id)
    )
    ctx.user_data.clear()
    return ConversationHandler.END
