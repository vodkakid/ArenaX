"""
Utilidades: horario, teclados, formateo — ArenaX v5
"""
from datetime import datetime
import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import BUSINESS_HOUR_OPEN, BUSINESS_HOUR_CLOSE, BANKS, GAME_MODES

VET = pytz.timezone("America/Caracas")


def is_business_hours() -> bool:
    now = datetime.now(VET)
    return BUSINESS_HOUR_OPEN <= now.hour < BUSINESS_HOUR_CLOSE


def business_hours_str() -> str:
    return "🕙 10:00 am — 10:00 pm (hora Venezuela)"


# ── Teclados jugador ──────────────────────────────────────────────────────────

def kb_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Competir",  callback_data="menu_compete"),
         InlineKeyboardButton("👤 Mi Perfil", callback_data="menu_profile")],
        [InlineKeyboardButton("📊 Ranking",   callback_data="menu_ranking"),
         InlineKeyboardButton("🏆 Torneos",   callback_data="menu_tournaments")],
        [InlineKeyboardButton("💸 Retirar",   callback_data="menu_withdraw"),
         InlineKeyboardButton("💰 Balance",   callback_data="menu_balance")],
    ])


def kb_compete_again():
    """Botón que aparece justo al terminar una partida."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚔️ Volver a competir", callback_data="menu_compete")],
        [InlineKeyboardButton("🏠 Menú principal",     callback_data="menu_main")],
    ])


def kb_terms():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Acepto los T&C", callback_data="tc_accept")],
        [InlineKeyboardButton("❌ No acepto",       callback_data="tc_reject")],
    ])


def kb_confirm_tag():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Sí, es mi tag",  callback_data="tag_ok")],
        [InlineKeyboardButton("❌ Corregir tag",   callback_data="tag_no")],
    ])


def kb_banks():
    rows = []
    for i in range(0, len(BANKS), 2):
        row = []
        for code, name in BANKS[i:i+2]:
            row.append(InlineKeyboardButton(f"{name[:22]}", callback_data=f"bank_{code}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Cancelar", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def kb_game_modes(back_data="menu_main"):
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"mode_{key}")]
        for key, label in GAME_MODES.items()
    ]
    buttons.append([InlineKeyboardButton("🔙 Volver", callback_data=back_data)])
    return InlineKeyboardMarkup(buttons)


def kb_confirm(yes_data, no_data, yes_label="✅ Confirmar", no_label="❌ Cancelar"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(yes_label, callback_data=yes_data),
         InlineKeyboardButton(no_label,  callback_data=no_data)],
    ])


def kb_back_to_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Menú principal", callback_data="menu_main")]
    ])


def kb_back_to_admin():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Volver al panel", callback_data="admin_back")]
    ])


def kb_profile_options():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Editar pago móvil",   callback_data="profile_edit")],
        [InlineKeyboardButton("🔗 Editar link amistad", callback_data="profile_edit_friend")],
        [InlineKeyboardButton("🏠 Menú principal",      callback_data="menu_main")],
    ])


def kb_in_queue():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Salir de la cola (reembolso)", callback_data="leave_queue")],
    ])


def kb_match_result(match_id: int):
    """Botones para reportar resultado de partida."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏆 Yo gané",  callback_data=f"result_win_{match_id}"),
         InlineKeyboardButton("😞 Yo perdí", callback_data=f"result_lose_{match_id}")],
    ])


def kb_send_proof(match_id: int):
    """Botón para enviar capture después de declarar victoria."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 Enviar capture de victoria",
                              callback_data=f"send_proof_{match_id}")],
    ])


# ── Teclados admin ────────────────────────────────────────────────────────────

def kb_admin_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Pagos",       callback_data="admin_payments"),
         InlineKeyboardButton("💸 Retiros",     callback_data="admin_withdrawals")],
        [InlineKeyboardButton("🎮 Cola",        callback_data="admin_queue"),
         InlineKeyboardButton("⚔️ Partidas",    callback_data="admin_matches")],
        [InlineKeyboardButton("👥 Jugadores",   callback_data="admin_players"),
         InlineKeyboardButton("📊 Stats",       callback_data="admin_stats")],
        [InlineKeyboardButton("💰 Finanzas",    callback_data="admin_finances"),
         InlineKeyboardButton("🏆 Torneos",     callback_data="admin_tournaments")],
        [InlineKeyboardButton("📢 Broadcast",   callback_data="admin_broadcast"),
         InlineKeyboardButton("📝 Textos",      callback_data="admin_edit_texts")],
        [InlineKeyboardButton("🔢 Límite wins", callback_data="admin_win_limit"),
         InlineKeyboardButton("🔄 Sheets",      callback_data="admin_sync_sheets")],
        [InlineKeyboardButton("⚖️ Disputas",    callback_data="admin_disputes")],
    ])


def kb_payment_review(payment_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Aprobar",  callback_data=f"pay_approve_{payment_id}"),
         InlineKeyboardButton("❌ Rechazar", callback_data=f"pay_reject_{payment_id}")],
    ])


def kb_withdrawal_review(wd_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Pago enviado", callback_data=f"wd_approve_{wd_id}"),
         InlineKeyboardButton("❌ Rechazar",     callback_data=f"wd_reject_{wd_id}")],
    ])


def kb_result_review(match_id: int, winner_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirmar victoria",
                              callback_data=f"res_approve_{match_id}_{winner_id}"),
         InlineKeyboardButton("❌ Rechazar",
                              callback_data=f"res_reject_{match_id}_{winner_id}")],
    ])


def kb_dispute_resolve(dispute_id: int, p1_id: int, p2_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏆 Gana J1", callback_data=f"disp_p1_{dispute_id}_{p1_id}"),
         InlineKeyboardButton("🏆 Gana J2", callback_data=f"disp_p2_{dispute_id}_{p2_id}")],
        [InlineKeyboardButton("❌ Anular (reembolso a ambos)",
                              callback_data=f"disp_void_{dispute_id}_0")],
    ])


def kb_manage_player(telegram_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Añadir saldo",   callback_data=f"mgmt_add_{telegram_id}"),
         InlineKeyboardButton("➖ Quitar saldo",   callback_data=f"mgmt_sub_{telegram_id}")],
        [InlineKeyboardButton("🚫 Suspender",      callback_data=f"mgmt_suspend_{telegram_id}"),
         InlineKeyboardButton("🔓 Reactivar",      callback_data=f"mgmt_activate_{telegram_id}")],
        [InlineKeyboardButton("⛔ Ban permanente", callback_data=f"mgmt_ban_{telegram_id}"),
         InlineKeyboardButton("🗑 Quitar de cola", callback_data=f"mgmt_dequeue_{telegram_id}")],
        [InlineKeyboardButton("🔙 Volver",         callback_data="admin_back")],
    ])


# ── Formateo ──────────────────────────────────────────────────────────────────

def fmt_usd(amount: float) -> str:
    return f"${amount:,.2f} USD"


def fmt_ves(amount: float) -> str:
    return f"Bs. {amount:,.2f}"


def fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso or "N/A"


GAME_MODE_LABELS = {
    "1v1":    "⚔️ 1vs1",
    "triple": "🃏 Triple Elixir",
}


def mode_label(mode: str) -> str:
    return GAME_MODE_LABELS.get(mode, mode)
