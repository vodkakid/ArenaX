"""
Tareas programadas: liquidación diaria a medianoche, reset del ranking.
Se puede integrar con APScheduler o usar el JobQueue de python-telegram-bot.
"""

import logging
from datetime import datetime
import pytz
import database as db
from config import ADMIN_IDS

logger = logging.getLogger(__name__)
VET = pytz.timezone("America/Caracas")


async def daily_liquidation(context):
    """
    Ejecutar a medianoche hora Venezuela.
    1. Notifica a jugadores con saldo pendiente que deben retirarlo.
    2. Resetea el contador de victorias diarias.
    3. Limpia la cola (partidas del día deben resolverse antes de las 12am).
    """
    now = datetime.now(VET).strftime("%Y-%m-%d %H:%M")
    logger.info(f"Iniciando liquidación diaria — {now}")

    # Resetear victorias del día
    db.reset_daily_wins()

    # Notificar a jugadores con saldo > 0 que el día terminó
    players = db.get_all_players()
    notified = 0
    for p in players:
        if p["balance_usd"] >= 0.01 and p["status"] == "active":
            try:
                await context.bot.send_message(
                    p["telegram_id"],
                    f"🌙 *Cierre del día ArenaX*\n\n"
                    f"Tu balance actual es *${p['balance_usd']:.2f} USD*.\n"
                    f"Si no retiraste hoy, tu saldo estará disponible mañana.\n\n"
                    f"¡Hasta mañana! Operamos de 10am a 10pm. 🏆",
                    parse_mode="Markdown"
                )
                notified += 1
            except Exception:
                pass

    # Notificar al admin
    for admin_id in ADMIN_IDS:
        try:
            stats = db.get_stats()
            fin   = db.get_finance_summary()
            await context.bot.send_message(
                admin_id,
                f"🌙 *Resumen del día — ArenaX*\n\n"
                f"⚔️ Partidas del día: {stats['today_matches']}\n"
                f"👥 Jugadores activos: {stats['active_players']}\n"
                f"💰 Saldo total jugadores: ${fin['total_player_balance']:.2f} USD\n"
                f"⏳ Retiros pendientes: {fin['pending_withdrawals']}\n\n"
                f"📊 Victorias diarias reseteadas.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error notificando admin en liquidación: {e}")

    logger.info(f"Liquidación completada. Notificados: {notified} jugadores.")


def setup_jobs(app):
    """
    Configura el scheduler de tareas.
    Llamar desde bot.py después de crear la Application.
    """
    from telegram.ext import CallbackContext

    job_queue = app.job_queue

    # Liquidación diaria a medianoche (00:00 Venezuela = 04:00 UTC)
    job_queue.run_daily(
        daily_liquidation,
        time=datetime.strptime("04:00", "%H:%M").time().replace(tzinfo=pytz.UTC),
        name="daily_liquidation"
    )

    logger.info("Jobs programados ✅")
