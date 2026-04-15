"""
Servicios externos: Tasa BCV, Google Sheets.
Google Sheets: crea hojas automáticamente, usa sheetId para escribir.
100% inmune al error 'Unable to parse range'.
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


# ── Tag CR ────────────────────────────────────────────────────────────────────

_TAG_RE = re.compile(r'^[0-9A-Z]{3,12}$')


def normalize_tag(tag: str) -> str:
    tag = tag.upper().strip()
    tag = re.sub(r'[^A-Z0-9]', '', tag)
    return '#' + tag


def is_valid_tag_format(tag: str) -> bool:
    clean = tag.lstrip('#')
    return bool(_TAG_RE.match(clean))


# ── Google Sheets ─────────────────────────────────────────────────────────────

_sheets_service = None

# Nombres de las hojas
SHEET_PLAYERS  = "Jugadores"
SHEET_MATCHES  = "Partidas"
SHEET_FINANCES = "Finanzas"


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


def _get_sheet_ids(service) -> dict:
    """Devuelve {nombre: sheetId} de todas las hojas existentes."""
    meta = service.spreadsheets().get(
        spreadsheetId=SHEETS_SPREADSHEET_ID
    ).execute()
    return {
        s["properties"]["title"]: s["properties"]["sheetId"]
        for s in meta.get("sheets", [])
    }


def _ensure_sheets(service) -> dict:
    """
    Asegura que las 3 hojas existan.
    Las crea si no están. Devuelve {nombre: sheetId}.
    """
    existing  = _get_sheet_ids(service)
    needed    = [SHEET_PLAYERS, SHEET_MATCHES, SHEET_FINANCES]
    to_create = [n for n in needed if n not in existing]

    if to_create:
        reqs = [{"addSheet": {"properties": {"title": n}}} for n in to_create]
        service.spreadsheets().batchUpdate(
            spreadsheetId=SHEETS_SPREADSHEET_ID,
            body={"requests": reqs}
        ).execute()
        logger.info(f"Hojas creadas: {to_create}")
        existing = _get_sheet_ids(service)

    return existing


def _write(service, sheet_id: int, rows: list):
    """
    Escribe datos en una hoja usando su sheetId numérico.
    No usa el nombre de la hoja — evita 100% el error 'Unable to parse range'.
    """
    # Construir celdas
    cell_rows = []
    for row in rows:
        cells = []
        for val in row:
            if val is None or val == "":
                cells.append({"userEnteredValue": {"stringValue": ""}})
            elif isinstance(val, bool):
                cells.append({"userEnteredValue": {"boolValue": val}})
            elif isinstance(val, (int, float)):
                cells.append({"userEnteredValue": {"numberValue": float(val)}})
            else:
                cells.append({"userEnteredValue": {"stringValue": str(val)}})
        cell_rows.append({"values": cells})

    # Limpiar hoja y escribir en una sola operación
    service.spreadsheets().batchUpdate(
        spreadsheetId=SHEETS_SPREADSHEET_ID,
        body={"requests": [
            # Limpiar
            {
                "updateCells": {
                    "range":  {"sheetId": sheet_id},
                    "fields": "userEnteredValue"
                }
            },
            # Escribir
            {
                "updateCells": {
                    "rows":   cell_rows,
                    "fields": "userEnteredValue",
                    "start":  {
                        "sheetId":     sheet_id,
                        "rowIndex":    0,
                        "columnIndex": 0
                    }
                }
            }
        ]}
    ).execute()


def sync_to_sheets() -> dict:
    """
    Sincroniza BD con Google Sheets.
    Crea las hojas si no existen.
    Usa sheetId numérico — inmune a problemas de nombres.
    """
    service = _get_sheets_service()
    if not service:
        return {
            "ok": False,
            "error": "Sin credenciales. Configura GOOGLE_CREDENTIALS_JSON en Railway."
        }

    try:
        sheet_map   = _ensure_sheets(service)
        players_id  = sheet_map.get(SHEET_PLAYERS)
        matches_id  = sheet_map.get(SHEET_MATCHES)
        finances_id = sheet_map.get(SHEET_FINANCES)

        if None in (players_id, matches_id, finances_id):
            return {"ok": False, "error": "No se encontraron las hojas."}

        # ── Jugadores ──────────────────────────────────────────────────────
        players = db.get_all_players()
        p_rows  = [[
            "ID Telegram", "Tag CR", "Nombre CR", "Teléfono", "Banco",
            "Cédula", "Balance USD", "V. Hoy", "D. Hoy",
            "Total V", "Total D", "% Victoria", "Racha", "Estado", "Registro"
        ]]
        for p in players:
            total = p["total_matches"]
            wins  = p["total_wins"]
            pct   = f"{round(wins/total*100)}%" if total > 0 else "0%"
            p_rows.append([
                p["telegram_id"], p["cr_tag"], p["cr_name"],
                p["phone"], p["bank_name"], p["cedula"],
                p["balance_usd"],
                p["wins_today"], p["losses_today"],
                p["total_wins"], p["total_losses"], pct,
                p["streak_current"],
                p["status"], p["registered_at"]
            ])
        _write(service, players_id, p_rows)

        # ── Partidas ───────────────────────────────────────────────────────
        matches = db.get_all_matches(limit=500)
        m_rows  = [["ID", "Jugador 1", "Jugador 2", "Modo",
                    "Ganador", "Premio USD", "Estado", "Fecha"]]
        for m in matches:
            m_rows.append([
                m["id"], m["p1_name"], m["p2_name"], m["game_mode"],
                m["winner_name"] or "En curso",
                m["prize_usd"] or 0,
                m["status"], m["created_at"]
            ])
        _write(service, matches_id, m_rows)

        # ── Finanzas ───────────────────────────────────────────────────────
        fin = db.get_finance_summary()
        t, w, mo = fin["today"], fin["week"], fin["month"]
        f_rows = [
            ["Métrica",                    "Valor"],
            ["── HOY ──",                  ""],
            ["Partidas",                   t["matches"]],
            ["Inscripciones (USD)",        t["inscriptions"]],
            ["Premios pagados (USD)",      t["prizes"]],
            ["Ganancia neta (USD)",        t["profit"]],
            ["── SEMANA ──",               ""],
            ["Partidas",                   w["matches"]],
            ["Inscripciones (USD)",        w["inscriptions"]],
            ["Ganancia neta (USD)",        w["profit"]],
            ["── MES ──",                  ""],
            ["Partidas",                   mo["matches"]],
            ["Inscripciones (USD)",        mo["inscriptions"]],
            ["Ganancia neta (USD)",        mo["profit"]],
            ["── TOTAL HISTÓRICO ──",      ""],
            ["Inscripciones (USD)",        fin["total_in"]],
            ["Premios pagados (USD)",      fin["total_prizes"]],
            ["Ganancia total (USD)",       fin["total_profit"]],
            ["Saldo jugadores (USD)",      fin["player_balance"]],
            ["Retiros pendientes",         fin["pending_withdrawals"]],
            ["Retiros pendientes (USD)",   fin["pending_wd_usd"]],
            ["Pagos pendientes",           fin["pending_payments"]],
            ["Última sync",                datetime.now().strftime("%Y-%m-%d %H:%M")],
        ]
        _write(service, finances_id, f_rows)

        logger.info(f"Sync OK — {len(players)} jugadores, {len(matches)} partidas")
        return {"ok": True, "players": len(players), "matches": len(matches)}

    except Exception as e:
        logger.error(f"Error sync Sheets: {e}")
        return {"ok": False, "error": str(e)}
