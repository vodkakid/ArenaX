import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN  = os.getenv("BOT_TOKEN", "")
ADMIN_ID   = int(os.getenv("ADMIN_ID", "0"))
ADMIN_IDS  = [ADMIN_ID]

GROUP_ID               = int(os.getenv("GROUP_ID", "0"))
TOPIC_ANNOUNCEMENTS_ID = int(os.getenv("TOPIC_ANNOUNCEMENTS_ID", "2"))
TOPIC_MATCHMAKING_ID   = int(os.getenv("TOPIC_MATCHMAKING_ID", "32"))
TOPIC_RESULTS_ID       = int(os.getenv("TOPIC_RESULTS_ID", "14"))
ADMIN_CHANNEL_ID       = int(os.getenv("ADMIN_CHANNEL_ID", "0"))

SHEETS_CREDENTIALS_FILE = os.getenv("SHEETS_CREDENTIALS_FILE", "credentials.json")
SHEETS_SPREADSHEET_ID   = os.getenv("SHEETS_SPREADSHEET_ID", "")

DATABASE_URL = os.getenv("DATABASE_URL", "arenax.db")

# ── Modelo económico ──────────────────────────────────────────────────────────
ENTRY_FEE_USD    = float(os.getenv("ENTRY_FEE_USD",    "1.50"))
WIN_PRIZE_USD    = float(os.getenv("WIN_PRIZE_USD",     "1.00"))
MIN_WITHDRAW_USD = float(os.getenv("MIN_WITHDRAW_USD",  "2.50"))
# Ganador recibe: WIN_PRIZE_USD + ENTRY_FEE_USD = $2.50
# ArenaX gana:   ENTRY_FEE_USD - WIN_PRIZE_USD  = $0.50 por partida

# ── Timeouts — Opción A ───────────────────────────────────────────────────────
RESULT_REMINDER_MIN = int(os.getenv("RESULT_REMINDER_MIN", "10"))  # recordatorio
RESULT_TIMEOUT_MIN  = int(os.getenv("RESULT_TIMEOUT_MIN",  "15"))  # timeout total

BUSINESS_HOUR_OPEN  = 10
BUSINESS_HOUR_CLOSE = 22

GAME_MODES = {
    "1v1":    "⚔️ 1vs1 — Duelo Clásico",
    "triple": "🃏 Triple Elixir",
}

BANKS = [
    ("0102", "Banco de Venezuela"),
    ("0104", "Venezolano de Crédito"),
    ("0105", "Mercantil"),
    ("0108", "Provincial BBVA"),
    ("0114", "Bancaribe"),
    ("0115", "Exterior"),
    ("0128", "Caroní"),
    ("0134", "Banesco"),
    ("0138", "Citibank"),
    ("0151", "BFC Banco Fondo Común"),
    ("0156", "100% Banco"),
    ("0161", "Bancrecer"),
    ("0163", "Banplus"),
    ("0166", "Banco Agrícola"),
    ("0168", "Bancamiga"),
    ("0169", "Mi Banco"),
    ("0171", "Activo"),
    ("0175", "Bicentenario"),
    ("0191", "Nacional de Crédito BNC"),
]

ARENAX_PAYMENT = {
    "bank":   os.getenv("ARENAX_BANK",   "Banesco (0134)"),
    "phone":  os.getenv("ARENAX_PHONE",  "0412-0000000"),
    "cedula": os.getenv("ARENAX_CEDULA", "V-00000000"),
    "name":   os.getenv("ARENAX_NAME",   "ArenaX"),
}
