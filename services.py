"""
Servicios externos: Tasa BCV, Google Sheets.
Sin ninguna dependencia de API de Clash Royale.
"""
import aiohttp
import logging
import re
import os
from datetime import datetime
from config import SHEETS_CREDENTIALS_FILE, SHEETS_SPREADSHEET_ID
import database as db

logger = logging.getLogger(__name__)

# ── Tasa BCV ──────────────────────────────────────────────────────────────────

_bcv_cache = {"rate": 0.0, "fetched_at": None}


async def get_bcv_rate() -> float:
    import time
    now = time.time()
    if _bcv_cache["fetched_at"] and (now - _bcv_cache["fetched_at"]) < 1800:
        return _bcv_cache["rate"]
    try:
        rate = await _fetch_bcv()
        if rate and rate > 0:
            _bcv_cache["rate"] = rate
            _bcv_cache["fetched_at"] = now
            db.set_setting("bcv_rate", str(rate))
            logger.info(f"Tasa BCV: {rate}")
            return rate
    except Exception as e:
        logger.warning(f"Error BCV: {e}")
    stored = db.get_setting("bcv_rate")
    try:
        v = float(stored)
        return v if v > 0 else 0.0
    except Exception:
        return 0.0


async def _fetch_bcv() -> float:
    url = "https://api.exchangerate-api.com/v4/latest/USD"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
            data = await r.json(content_type=None)
            return float(data.get("rates", {}).get("VES", 0))


def format_rate(rate: float) -> str:
    return f"Bs. {rate:,.2f}"


def usd_to_ves(usd: float, rate: float) -> float:
    return round(usd * rate, 2)


# ── Validación de tag CR (solo formato, sin API) ──────────────────────────────

_TAG_RE = re.compile(r'^[0-9A-Z]{3,12}$')


def normalize_tag(tag: str) -> str:
    """Limpia el tag: mayúsculas, sin espacios, sin #, solo alfanumérico."""
    tag = tag.upper().strip()
    tag = re.sub(r'[^A-Z0-9]', '', tag)
    return '#' + tag


def is_valid_tag_format(tag: str) -> bool:
    """Verifica que el tag tenga formato válido de CR (3-12 caracteres alfanuméricos)."""
    clean = tag.lstrip('#')
    return bool(_TAG_RE.match(clean))


# ── Google Sheets ─────────────────────────────────────────────────────────────

_sheets_service = None


def _get_sheets_service():
    global _sheets_service
    if _sheets_service:
        return _sheets_service
    try:
        import json
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            info = json.loads(creds_json)
            creds = Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
        else:
            creds = Credentials.from_service_account_file(
                SHEETS_CREDENTIALS_FILE,
                scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
        _sheets_service = build("sheets", "v4", credentials=creds)
        return _sheets_service
    except Exception as e:
        logger.error(f"Error Google Sheets: {e}")
        return None


def sync_to_sheets() -> dict:
    service = _get_sheets_service()
    if not service:
        return {"ok": False,
                "error": "Sin credenciales. Configura GOOGLE_CREDENTIALS_JSON en Railway."}
    try:
        sheets = service.spreadsheets()

        players = db.get_all_players()
        rows = [["ID Telegram", "Tag CR", "Nombre CR", "Teléfono", "Banco",
                 "Cédula", "Balance USD", "Victorias Hoy", "Total Victorias",
                 "Estado", "Registro"]]
        for p in players:
            rows.append([p["telegram_id"], p["cr_tag"], p["cr_name"],
                         p["phone"], p["bank_name"], p["cedula"],
                         p["balance_usd"], p["wins_today"], p["total_wins"],
                         p["status"], p["registered_at"]])
        sheets.values().update(
            spreadsheetId=SHEETS_SPREADSHEET_ID, range="Jugadores!A1",
            valueInputOption="USER_ENTERED", body={"values": rows}
        ).execute()

        matches = db.get_all_matches(limit=500)
        mrows = [["ID", "Jugador 1", "Jugador 2", "Modo", "Ganador", "Premio", "Estado", "Fecha"]]
        for m in matches:
            mrows.append([m["id"], m["p1_name"], m["p2_name"], m["game_mode"],
                          m["winner_name"] or "N/A", m["prize_usd"] or 0,
                          m["status"], m["created_at"]])
        sheets.values().update(
            spreadsheetId=SHEETS_SPREADSHEET_ID, range="Partidas!A1",
            valueInputOption="USER_ENTERED", body={"values": mrows}
        ).execute()

        fin = db.get_finance_summary()
        frows = [
            ["Métrica", "Valor"],
            ["Total ingresado (USD)", fin["total_in"]],
            ["Total retirado (USD)", fin["total_out"]],
            ["Pagos pendientes", fin["pending_payments"]],
            ["Retiros pendientes", fin["pending_withdrawals"]],
            ["Saldo jugadores (USD)", fin["total_player_balance"]],
            ["Sincronizado", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ]
        sheets.values().update(
            spreadsheetId=SHEETS_SPREADSHEET_ID, range="Finanzas!A1",
            valueInputOption="USER_ENTERED", body={"values": frows}
        ).execute()

        return {"ok": True, "players": len(players), "matches": len(matches)}
    except Exception as e:
        logger.error(f"Error sync Sheets: {e}")
        return {"ok": False, "error": str(e)}
