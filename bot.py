"""
ArenaX Bot v6.1 — Correcciones críticas
"""
import logging
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters
)
from config import BOT_TOKEN
from handlers import registration, competition, profile, admin, common
from database import init_db
from scheduler import setup_jobs

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # ── /resetear ─────────────────────────────────────────────────────────────
    reset_conv = ConversationHandler(
        entry_points=[CommandHandler("resetear", registration.cmd_resetear)],
        states={
            registration.RESET_CONFIRM: [
                CallbackQueryHandler(
                    registration.handle_reset_confirm, pattern="^reset_"
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", common.cmd_cancel)],
        per_message=False,
        allow_reentry=True,
    )

    # ── Registro ───────────────────────────────────────────────────────────────
    reg_conv = ConversationHandler(
        entry_points=[CommandHandler("start", registration.cmd_start)],
        states={
            registration.WAITING_TC:       [
                CallbackQueryHandler(registration.accept_tc,  pattern="^tc_accept$"),
                CallbackQueryHandler(registration.reject_tc,  pattern="^tc_reject$"),
            ],
            registration.WAITING_TAG:      [
                MessageHandler(filters.TEXT & ~filters.COMMAND, registration.receive_tag)
            ],
            registration.CONFIRM_TAG:      [
                CallbackQueryHandler(registration.confirm_tag, pattern="^(tag_ok|tag_no)$")
            ],
            registration.WAITING_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, registration.receive_username)
            ],
            registration.WAITING_PHONE:    [
                MessageHandler(filters.TEXT & ~filters.COMMAND, registration.receive_phone)
            ],
            registration.WAITING_CEDULA:   [
                MessageHandler(filters.TEXT & ~filters.COMMAND, registration.receive_cedula)
            ],
            registration.WAITING_BANK:     [
                CallbackQueryHandler(registration.receive_bank, pattern="^bank_")
            ],
            registration.WAITING_FRIEND:   [
                MessageHandler(filters.TEXT & ~filters.COMMAND, registration.receive_friend_link)
            ],
        },
        fallbacks=[CommandHandler("cancel", common.cmd_cancel)],
        per_message=False,
        allow_reentry=True,
    )

    # ── Competir ───────────────────────────────────────────────────────────────
    comp_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(competition.start_compete, pattern="^menu_compete$")
        ],
        states={
            competition.SELECT_MODE:     [
                CallbackQueryHandler(competition.select_mode, pattern="^mode_"),
            ],
            competition.WAITING_PAYMENT: [
                MessageHandler(filters.PHOTO, competition.receive_payment_proof),
                CallbackQueryHandler(competition.pay_from_balance,
                                     pattern="^pay_from_balance$"),
                CallbackQueryHandler(competition.pay_mobile,
                                     pattern="^pay_mobile$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", common.cmd_cancel),
            CallbackQueryHandler(common.back_to_menu, pattern="^menu_main$"),
        ],
        per_message=False,
        allow_reentry=True,
    )

    # ── Capture de disputa — COMPLETAMENTE SEPARADO del flow de pago ──────────
    dispute_proof_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                competition.start_dispute_proof,
                pattern="^submit_dispute_proof_"
            )
        ],
        states={
            competition.WAITING_DISPUTE_PROOF: [
                MessageHandler(filters.PHOTO, competition.receive_dispute_proof)
            ],
        },
        fallbacks=[CommandHandler("cancel", common.cmd_cancel)],
        per_message=False,
        allow_reentry=True,
    )

    # ── Editar perfil ──────────────────────────────────────────────────────────
    edit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(profile.start_edit, pattern="^profile_edit$")
        ],
        states={
            profile.EDIT_PHONE:  [
                MessageHandler(filters.TEXT & ~filters.COMMAND, profile.edit_phone)
            ],
            profile.EDIT_CEDULA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, profile.edit_cedula)
            ],
            profile.EDIT_BANK:   [
                CallbackQueryHandler(profile.edit_bank, pattern="^bank_")
            ],
            profile.EDIT_FRIEND: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, profile.edit_friend)
            ],
        },
        fallbacks=[CallbackQueryHandler(common.back_to_menu, pattern="^menu_main$")],
        per_message=False,
        allow_reentry=True,
    )

    # ── Retiro ─────────────────────────────────────────────────────────────────
    withdraw_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(profile.start_withdraw, pattern="^menu_withdraw$")
        ],
        states={
            profile.WITHDRAW_AMOUNT:  [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               profile.confirm_withdraw)
            ],
            profile.WITHDRAW_CONFIRM: [
                CallbackQueryHandler(
                    profile.execute_withdraw,
                    pattern="^(withdraw_ok|withdraw_no)$"
                )
            ],
        },
        fallbacks=[CallbackQueryHandler(common.back_to_menu, pattern="^menu_main$")],
        per_message=False,
        allow_reentry=True,
    )

    # ── Torneo ─────────────────────────────────────────────────────────────────
    tournament_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin.create_tournament_start,
                                 pattern="^admin_tournament_create$")
        ],
        states={
            admin.TOURN_NAME:    [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin.tourn_name),
                CallbackQueryHandler(admin.back_to_admin, pattern="^admin_back$"),
            ],
            admin.TOURN_MODE:    [
                CallbackQueryHandler(admin.tourn_mode,    pattern="^mode_"),
                CallbackQueryHandler(admin.back_to_admin, pattern="^admin_back$"),
            ],
            admin.TOURN_FEE:     [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin.tourn_fee),
                CallbackQueryHandler(admin.back_to_admin, pattern="^admin_back$"),
            ],
            admin.TOURN_PRIZE:   [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin.tourn_prize),
                CallbackQueryHandler(admin.back_to_admin, pattern="^admin_back$"),
            ],
            admin.TOURN_CONFIRM: [
                CallbackQueryHandler(admin.tourn_confirm,
                                     pattern="^(tourn_ok|tourn_cancel)$")
            ],
        },
        fallbacks=[CallbackQueryHandler(admin.back_to_admin, pattern="^admin_back$")],
        per_message=False,
        allow_reentry=True,
    )

    # ── Broadcast + Límite victorias — UN SOLO handler para evitar conflictos ──
    # Ambos usan ADMIN_TEXT_INPUT y se distinguen por user_data["admin_input_type"]
    admin_input_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin.broadcast_start,  pattern="^admin_broadcast$"),
            CallbackQueryHandler(admin.admin_win_limit,  pattern="^admin_win_limit$"),
        ],
        states={
            admin.ADMIN_TEXT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               admin.handle_admin_text_input)
            ],
            admin.BROADCAST_OK: [
                CallbackQueryHandler(
                    admin.broadcast_send,
                    pattern="^(broadcast_yes|broadcast_no)$"
                )
            ],
        },
        fallbacks=[CallbackQueryHandler(admin.back_to_admin, pattern="^admin_back$")],
        per_message=False,
        allow_reentry=True,
    )
    broadcast_conv  = admin_input_conv  # alias para mantener la lista
    win_limit_conv  = admin_input_conv  # alias — mismo objeto, no se registra dos veces

    # ── Gestionar jugador ──────────────────────────────────────────────────────
    manage_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin.manage_player_search,
                                 pattern="^admin_manage_player$")
        ],
        states={
            admin.MANAGE_SEARCH:  [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               admin.manage_player_found)
            ],
            admin.MANAGE_ACTION:  [
                CallbackQueryHandler(admin.manage_player_action, pattern="^mgmt_")
            ],
            admin.MANAGE_BALANCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               admin.manage_balance_apply)
            ],
        },
        fallbacks=[CallbackQueryHandler(admin.back_to_admin, pattern="^admin_back$")],
        per_message=False,
        allow_reentry=True,
    )

    # ── Editar textos ──────────────────────────────────────────────────────────
    texts_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin.edit_texts_start,
                                 pattern="^admin_edit_texts$")
        ],
        states={
            admin.EDIT_TEXT_SELECT: [
                CallbackQueryHandler(admin.edit_text_select, pattern="^text_"),
                CallbackQueryHandler(admin.edit_texts_start,
                                     pattern="^admin_edit_texts$"),
            ],
            admin.EDIT_TEXT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               admin.edit_text_save),
                CallbackQueryHandler(admin.edit_texts_start,
                                     pattern="^admin_edit_texts$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(admin.back_to_admin, pattern="^admin_back$")],
        per_message=False,
        allow_reentry=True,
    )

    # win_limit_conv ya está incluido en admin_input_conv ↑

    # ── Disputa manual ─────────────────────────────────────────────────────────
    dispute_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(competition.open_dispute, pattern="^dispute_")
        ],
        states={
            competition.DISPUTE_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               competition.submit_dispute)
            ],
        },
        fallbacks=[CommandHandler("cancel", common.cmd_cancel)],
        per_message=False,
        allow_reentry=True,
    )

    # ── Registrar todos ────────────────────────────────────────────────────────
    for conv in [
        reset_conv, reg_conv,
        dispute_proof_conv,   # ← ANTES de comp_conv para tener prioridad
        comp_conv,
        edit_conv, withdraw_conv,
        tournament_conv, admin_input_conv, manage_conv,
        texts_conv,
        dispute_conv,
    ]:
        app.add_handler(conv)

    # ── Comandos globales ──────────────────────────────────────────────────────
    app.add_handler(CommandHandler("menu",  common.cmd_menu))
    app.add_handler(CommandHandler("admin", admin.cmd_admin_panel))
    app.add_handler(CommandHandler("sync",  admin.cmd_sync_sheets))

    # ── Menú jugador ───────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(profile.show_profile,
                                         pattern="^menu_profile$"))
    app.add_handler(CallbackQueryHandler(profile.show_balance,
                                         pattern="^menu_balance$"))
    app.add_handler(CallbackQueryHandler(profile.show_ranking,
                                         pattern="^menu_ranking$"))
    app.add_handler(CallbackQueryHandler(profile.show_tournaments,
                                         pattern="^menu_tournaments$"))
    app.add_handler(CallbackQueryHandler(common.back_to_menu,
                                         pattern="^menu_main$"))

    # ── Resultados "Yo gané / Yo perdí" ───────────────────────────────────────
    app.add_handler(CallbackQueryHandler(competition.handle_result,
                                         pattern="^result_(win|lose)_"))

    # ── Panel admin ────────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(admin.admin_payments,
                                         pattern="^admin_payments$"))
    app.add_handler(CallbackQueryHandler(admin.admin_withdrawals,
                                         pattern="^admin_withdrawals$"))
    app.add_handler(CallbackQueryHandler(admin.admin_queue,
                                         pattern="^admin_queue$"))
    app.add_handler(CallbackQueryHandler(admin.admin_matches,
                                         pattern="^admin_matches$"))
    app.add_handler(CallbackQueryHandler(admin.admin_finances,
                                         pattern="^admin_finances$"))
    app.add_handler(CallbackQueryHandler(admin.admin_players,
                                         pattern="^admin_players$"))
    app.add_handler(CallbackQueryHandler(admin.admin_stats,
                                         pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin.admin_tournaments,
                                         pattern="^admin_tournaments$"))
    app.add_handler(CallbackQueryHandler(admin.admin_disputes,
                                         pattern="^admin_disputes$"))
    app.add_handler(CallbackQueryHandler(admin.admin_sync_sheets,
                                         pattern="^admin_sync_sheets$"))
    app.add_handler(CallbackQueryHandler(admin.back_to_admin,
                                         pattern="^admin_back$"))

    # ── Aprobar / rechazar ─────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(admin.approve_payment,
                                         pattern="^pay_approve_"))
    app.add_handler(CallbackQueryHandler(admin.reject_payment,
                                         pattern="^pay_reject_"))
    app.add_handler(CallbackQueryHandler(admin.approve_withdraw,
                                         pattern="^wd_approve_"))
    app.add_handler(CallbackQueryHandler(admin.reject_withdraw,
                                         pattern="^wd_reject_"))
    app.add_handler(CallbackQueryHandler(admin.approve_result,
                                         pattern="^res_approve_"))
    app.add_handler(CallbackQueryHandler(admin.reject_result,
                                         pattern="^res_reject_"))
    app.add_handler(CallbackQueryHandler(admin.resolve_dispute,
                                         pattern="^disp_"))
    app.add_handler(CallbackQueryHandler(admin.remove_from_queue,
                                         pattern="^queue_remove_"))

    # ── Cola ───────────────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(competition.leave_queue,
                                         pattern="^leave_queue$"))

    # ── Handler global para callbacks obsoletos — SIEMPRE AL FINAL ────────────
    app.add_handler(CallbackQueryHandler(common.handle_stale_callback))

    setup_jobs(app)
    logger.info("ArenaX Bot v6.1 iniciado ✅")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"]
    )


if __name__ == "__main__":
    main()
