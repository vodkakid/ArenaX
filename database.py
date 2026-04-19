"""
Base de datos SQLite — ArenaX v7
- started_at en matches para jobs persistentes
- Estadísticas solo de partidas completadas
- get_orphan_matches para recuperación al arrancar
"""
import os
import sqlite3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _resolve_db_path():
    vol = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if vol:
        return os.path.join(vol, "arenax.db")
    return os.getenv("DATABASE_URL", "arenax.db")


_DB_PATH = _resolve_db_path()


def get_conn():
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS players (
        telegram_id    INTEGER PRIMARY KEY,
        username       TEXT,
        cr_tag         TEXT UNIQUE NOT NULL,
        cr_name        TEXT,
        friend_link    TEXT,
        phone          TEXT,
        cedula         TEXT,
        bank_code      TEXT,
        bank_name      TEXT,
        balance_usd    REAL DEFAULT 0.0,
        wins_today     INTEGER DEFAULT 0,
        losses_today   INTEGER DEFAULT 0,
        total_wins     INTEGER DEFAULT 0,
        total_losses   INTEGER DEFAULT 0,
        total_matches  INTEGER DEFAULT 0,
        streak_current INTEGER DEFAULT 0,
        streak_best    INTEGER DEFAULT 0,
        status         TEXT DEFAULT 'active',
        registered_at  TEXT DEFAULT (datetime('now')),
        last_active    TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS queue (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL,
        game_mode   TEXT NOT NULL,
        payment_id  INTEGER,
        entered_at  TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(telegram_id) REFERENCES players(telegram_id)
    );
    CREATE TABLE IF NOT EXISTS payments (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id   INTEGER NOT NULL,
        game_mode     TEXT NOT NULL,
        amount_usd    REAL NOT NULL,
        amount_ves    REAL NOT NULL,
        bcv_rate      REAL NOT NULL,
        proof_file_id TEXT,
        status        TEXT DEFAULT 'pending',
        created_at    TEXT DEFAULT (datetime('now')),
        reviewed_at   TEXT,
        reviewed_by   INTEGER,
        FOREIGN KEY(telegram_id) REFERENCES players(telegram_id)
    );
    CREATE TABLE IF NOT EXISTS matches (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        player1_id      INTEGER NOT NULL,
        player2_id      INTEGER NOT NULL,
        game_mode       TEXT NOT NULL,
        winner_id       INTEGER,
        prize_usd       REAL DEFAULT 0,
        status          TEXT DEFAULT 'active',
        result_proof_p1 TEXT,
        result_proof_p2 TEXT,
        started_at      TEXT DEFAULT (datetime('now')),
        ended_at        TEXT,
        FOREIGN KEY(player1_id) REFERENCES players(telegram_id),
        FOREIGN KEY(player2_id) REFERENCES players(telegram_id)
    );
    CREATE TABLE IF NOT EXISTS match_reports (
        match_id    INTEGER NOT NULL,
        player_id   INTEGER NOT NULL,
        outcome     TEXT NOT NULL,
        reported_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY(match_id, player_id)
    );
    CREATE TABLE IF NOT EXISTS transactions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL,
        type        TEXT NOT NULL,
        amount_usd  REAL NOT NULL,
        description TEXT,
        match_id    INTEGER,
        status      TEXT DEFAULT 'completed',
        created_at  TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(telegram_id) REFERENCES players(telegram_id)
    );
    CREATE TABLE IF NOT EXISTS withdrawals (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL,
        amount_usd  REAL NOT NULL,
        amount_ves  REAL NOT NULL,
        bcv_rate    REAL NOT NULL,
        phone       TEXT,
        bank_name   TEXT,
        cedula      TEXT,
        status      TEXT DEFAULT 'pending',
        created_at  TEXT DEFAULT (datetime('now')),
        reviewed_at TEXT,
        FOREIGN KEY(telegram_id) REFERENCES players(telegram_id)
    );
    CREATE TABLE IF NOT EXISTS disputes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id    INTEGER NOT NULL,
        reporter_id INTEGER NOT NULL,
        reason      TEXT,
        status      TEXT DEFAULT 'open',
        resolution  TEXT,
        created_at  TEXT DEFAULT (datetime('now')),
        resolved_at TEXT,
        FOREIGN KEY(match_id) REFERENCES matches(id)
    );
    CREATE TABLE IF NOT EXISTS tournaments (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT NOT NULL,
        game_mode  TEXT NOT NULL,
        entry_fee  REAL DEFAULT 0.0,
        prize_usd  REAL NOT NULL,
        max_wins   INTEGER DEFAULT 3,
        status     TEXT DEFAULT 'upcoming',
        start_date TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS bot_texts (
        key        TEXT PRIMARY KEY,
        value      TEXT NOT NULL,
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)
    defaults_texts = {
        "welcome": (
            "🏆 *¡Bienvenido a ArenaX!*\n\n"
            "La comunidad de competencia skill-based para Clash Royale "
            "donde puedes ganar dinero real.\n\n"
            "Compite, gana y cobra. ¡Es hora de demostrar tu nivel!"
        ),
        "terms": (
            "📋 *TÉRMINOS Y CONDICIONES — ArenaX*\n\n"
            "1. Debes tener 18 años o más para participar.\n"
            "2. Cada inscripción cuesta *$1.50 USD* a tasa BCV del día.\n"
            "3. El ganador recibe *$1.00 USD* neto + recupera su inscripción de $1.50.\n"
            "4. Total para el ganador: *$2.50 USD*.\n"
            "5. Los saldos se liquidan antes de las 12am.\n"
            "6. El mínimo de retiro es de *$2.50 USD*.\n"
            "7. Horario: *10am a 10pm* (hora Venezuela).\n"
            "8. El uso de hacks resulta en ban permanente.\n"
            "9. Tienes *15 minutos* para reportar el resultado.\n"
            "10. Las decisiones del administrador son definitivas."
        ),
        "payment_instructions": (
            "💳 *Instrucciones de pago*\n\n"
            "Realiza el pago móvil a los datos de ArenaX.\n"
            "Luego envía el *capture* del comprobante.\n\n"
            "⚠️ El monto debe ser exacto en bolívares."
        ),
        "match_rules": (
            "⚔️ *Reglas*\n\n"
            "1. Presiona el botón para agregar a tu oponente como amigo.\n"
            "2. Envíale una *batalla amistosa* del modo acordado.\n"
            "3. Al terminar reporta: *Yo gané* o *Yo perdí*.\n"
            "4. Tienes *15 minutos* para reportar.\n"
            "5. Si hay conflicto, ambos envían capture y el admin decide."
        ),
    }
    defaults_settings = {
        "bcv_rate": "0", "win_limit_day": "10",
        "entry_fee_usd": "1.50", "min_withdraw": "2.50",
    }
    for k, v in defaults_texts.items():
        c.execute("INSERT OR IGNORE INTO bot_texts(key,value) VALUES(?,?)", (k, v))
    for k, v in defaults_settings.items():
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    conn.commit()
    conn.close()
    logger.info("Base de datos inicializada ✅")


# ── Settings ──────────────────────────────────────────────────────────────────
def get_setting(key):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else ""

def set_setting(key, value):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))
        conn.commit()

def get_text(key):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM bot_texts WHERE key=?", (key,)).fetchone()
        return row["value"] if row else f"[{key}]"

def set_text(key, value):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO bot_texts(key,value,updated_at) VALUES(?,?,?)",
                     (key, value, datetime.now().isoformat()))
        conn.commit()


# ── Jugadores ─────────────────────────────────────────────────────────────────
def get_player(telegram_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM players WHERE telegram_id=?", (telegram_id,)).fetchone()

def get_player_by_tag(tag):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM players WHERE cr_tag=?", (tag.upper(),)).fetchone()

def create_player(telegram_id, username, cr_tag, cr_name,
                  friend_link, phone, cedula, bank_code, bank_name):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO players(telegram_id,username,cr_tag,cr_name,friend_link,
                                phone,cedula,bank_code,bank_name)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, (telegram_id, username, cr_tag.upper(), cr_name,
              friend_link, phone, cedula, bank_code, bank_name))
        conn.commit()

def update_player_payment_data(telegram_id, phone, cedula, bank_code, bank_name):
    with get_conn() as conn:
        conn.execute("UPDATE players SET phone=?,cedula=?,bank_code=?,bank_name=? WHERE telegram_id=?",
                     (phone, cedula, bank_code, bank_name, telegram_id))
        conn.commit()

def update_player_friend_link(telegram_id, friend_link):
    with get_conn() as conn:
        conn.execute("UPDATE players SET friend_link=? WHERE telegram_id=?", (friend_link, telegram_id))
        conn.commit()

def update_player_balance(telegram_id, delta_usd, description="", tx_type="credit", match_id=None):
    with get_conn() as conn:
        conn.execute("UPDATE players SET balance_usd=balance_usd+? WHERE telegram_id=?", (delta_usd, telegram_id))
        conn.execute("INSERT INTO transactions(telegram_id,type,amount_usd,description,match_id) VALUES(?,?,?,?,?)",
                     (telegram_id, tx_type, delta_usd, description, match_id))
        conn.commit()

def set_player_status(telegram_id, status):
    with get_conn() as conn:
        conn.execute("UPDATE players SET status=? WHERE telegram_id=?", (status, telegram_id))
        conn.commit()

def get_all_players():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM players ORDER BY registered_at DESC").fetchall()

def get_daily_ranking():
    with get_conn() as conn:
        return conn.execute("""
            SELECT cr_name,wins_today,losses_today,total_wins,total_losses,balance_usd,streak_current
            FROM players WHERE wins_today>0 OR losses_today>0
            ORDER BY wins_today DESC,total_wins DESC LIMIT 20
        """).fetchall()

def reset_daily_wins():
    with get_conn() as conn:
        conn.execute("UPDATE players SET wins_today=0,losses_today=0")
        conn.commit()


# ── Cola ──────────────────────────────────────────────────────────────────────
def add_to_queue(telegram_id, game_mode, payment_id):
    with get_conn() as conn:
        conn.execute("INSERT INTO queue(telegram_id,game_mode,payment_id) VALUES(?,?,?)",
                     (telegram_id, game_mode, payment_id))
        conn.commit()

def remove_from_queue(telegram_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM queue WHERE telegram_id=?", (telegram_id,))
        conn.commit()

def get_queue():
    with get_conn() as conn:
        return conn.execute("""
            SELECT q.*,p.cr_name,p.friend_link,p.username
            FROM queue q JOIN players p ON q.telegram_id=p.telegram_id
            ORDER BY q.entered_at
        """).fetchall()

def find_match_in_queue(game_mode, exclude_id):
    with get_conn() as conn:
        return conn.execute("""
            SELECT q.*,p.cr_name,p.friend_link,p.username,p.telegram_id as tid
            FROM queue q JOIN players p ON q.telegram_id=p.telegram_id
            WHERE q.game_mode=? AND q.telegram_id!=?
            ORDER BY q.entered_at LIMIT 1
        """, (game_mode, exclude_id)).fetchone()

def is_in_queue(telegram_id):
    with get_conn() as conn:
        return conn.execute("SELECT 1 FROM queue WHERE telegram_id=?", (telegram_id,)).fetchone() is not None


# ── Pagos ─────────────────────────────────────────────────────────────────────
def create_payment(telegram_id, game_mode, amount_usd, amount_ves, bcv_rate, proof_file_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO payments(telegram_id,game_mode,amount_usd,amount_ves,bcv_rate,proof_file_id) VALUES(?,?,?,?,?,?)",
                  (telegram_id, game_mode, amount_usd, amount_ves, bcv_rate, proof_file_id))
        conn.commit()
        return c.lastrowid

def get_payment(payment_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()

def update_payment_status(payment_id, status, reviewed_by=None):
    with get_conn() as conn:
        conn.execute("UPDATE payments SET status=?,reviewed_at=?,reviewed_by=? WHERE id=?",
                     (status, datetime.now().isoformat(), reviewed_by, payment_id))
        conn.commit()

def get_pending_payments():
    with get_conn() as conn:
        return conn.execute("""
            SELECT pay.*,p.cr_name,p.username
            FROM payments pay JOIN players p ON pay.telegram_id=p.telegram_id
            WHERE pay.status='pending' ORDER BY pay.created_at
        """).fetchall()


# ── Partidas ──────────────────────────────────────────────────────────────────
def create_match(player1_id, player2_id, game_mode, prize_usd=0):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO matches(player1_id,player2_id,game_mode,prize_usd,started_at) VALUES(?,?,?,?,?)",
                  (player1_id, player2_id, game_mode, prize_usd, datetime.now().isoformat()))
        conn.commit()
        return c.lastrowid

def get_match(match_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()

def get_active_match_for_player(telegram_id):
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM matches
            WHERE (player1_id=? OR player2_id=?) AND status IN ('active','disputed')
            ORDER BY started_at DESC LIMIT 1
        """, (telegram_id, telegram_id)).fetchone()

def get_orphan_matches(timeout_minutes: int):
    """Partidas activas más viejas que timeout_minutes — para recuperar al arrancar."""
    cutoff = (datetime.now() - timedelta(minutes=timeout_minutes)).isoformat()
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM matches WHERE status='active' AND started_at<=?", (cutoff,)
        ).fetchall()

def update_match_status(match_id, status):
    with get_conn() as conn:
        conn.execute("UPDATE matches SET status=? WHERE id=?", (status, match_id))
        conn.commit()

def set_match_result_proof(match_id, player_id, file_id):
    match = get_match(match_id)
    if not match:
        return
    col = "result_proof_p1" if match["player1_id"] == player_id else "result_proof_p2"
    with get_conn() as conn:
        conn.execute(f"UPDATE matches SET {col}=? WHERE id=?", (file_id, match_id))
        conn.commit()

def finalize_match(match_id, winner_id):
    with get_conn() as conn:
        conn.execute("UPDATE matches SET winner_id=?,status='completed',ended_at=? WHERE id=?",
                     (winner_id, datetime.now().isoformat(), match_id))
        match = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        if match:
            loser_id = match["player2_id"] if match["player1_id"] == winner_id else match["player1_id"]
            conn.execute("""
                UPDATE players SET wins_today=wins_today+1,total_wins=total_wins+1,
                total_matches=total_matches+1,streak_current=streak_current+1,
                streak_best=MAX(streak_best,streak_current+1),last_active=?
                WHERE telegram_id=?
            """, (datetime.now().isoformat(), winner_id))
            conn.execute("""
                UPDATE players SET losses_today=losses_today+1,total_losses=total_losses+1,
                total_matches=total_matches+1,streak_current=0,last_active=?
                WHERE telegram_id=?
            """, (datetime.now().isoformat(), loser_id))
        conn.commit()

def get_all_matches(limit=50):
    """Partidas ordenadas: completadas primero, luego disputadas, activas, anuladas."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT m.*,p1.cr_name as p1_name,p2.cr_name as p2_name,pw.cr_name as winner_name
            FROM matches m
            JOIN players p1 ON m.player1_id=p1.telegram_id
            JOIN players p2 ON m.player2_id=p2.telegram_id
            LEFT JOIN players pw ON m.winner_id=pw.telegram_id
            ORDER BY
                CASE m.status
                    WHEN 'completed' THEN 1
                    WHEN 'disputed'  THEN 2
                    WHEN 'active'    THEN 3
                    WHEN 'voided'    THEN 4
                END,
                m.started_at DESC
            LIMIT ?
        """, (limit,)).fetchall()


# ── Reportes ──────────────────────────────────────────────────────────────────
def set_match_report(match_id, player_id, outcome):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO match_reports(match_id,player_id,outcome) VALUES(?,?,?)",
                     (match_id, player_id, outcome))
        conn.commit()

def get_match_report(match_id, player_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM match_reports WHERE match_id=? AND player_id=?",
                            (match_id, player_id)).fetchone()


# ── Retiros ───────────────────────────────────────────────────────────────────
def create_withdrawal(telegram_id, amount_usd, amount_ves, bcv_rate, phone, bank_name, cedula):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO withdrawals(telegram_id,amount_usd,amount_ves,bcv_rate,phone,bank_name,cedula) VALUES(?,?,?,?,?,?,?)",
                  (telegram_id, amount_usd, amount_ves, bcv_rate, phone, bank_name, cedula))
        conn.execute("UPDATE players SET balance_usd=balance_usd-? WHERE telegram_id=?", (amount_usd, telegram_id))
        conn.commit()
        return c.lastrowid

def get_withdrawal(wd_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM withdrawals WHERE id=?", (wd_id,)).fetchone()

def get_pending_withdrawals():
    with get_conn() as conn:
        return conn.execute("""
            SELECT wd.*,p.cr_name,p.username FROM withdrawals wd
            JOIN players p ON wd.telegram_id=p.telegram_id
            WHERE wd.status='pending' ORDER BY wd.created_at
        """).fetchall()

def update_withdrawal_status(wd_id, status):
    with get_conn() as conn:
        if status == "rejected":
            wd = conn.execute("SELECT * FROM withdrawals WHERE id=?", (wd_id,)).fetchone()
            if wd:
                conn.execute("UPDATE players SET balance_usd=balance_usd+? WHERE telegram_id=?",
                             (wd["amount_usd"], wd["telegram_id"]))
        conn.execute("UPDATE withdrawals SET status=?,reviewed_at=? WHERE id=?",
                     (status, datetime.now().isoformat(), wd_id))
        conn.commit()


# ── Disputas ──────────────────────────────────────────────────────────────────
def create_dispute(match_id, reporter_id, reason):
    with get_conn() as conn:
        conn.execute("UPDATE matches SET status='disputed' WHERE id=?", (match_id,))
        c = conn.cursor()
        c.execute("INSERT INTO disputes(match_id,reporter_id,reason) VALUES(?,?,?)",
                  (match_id, reporter_id, reason))
        conn.commit()
        return c.lastrowid

def get_open_disputes():
    with get_conn() as conn:
        return conn.execute("""
            SELECT d.*,p.cr_name as reporter_name,m.player1_id,m.player2_id,m.game_mode
            FROM disputes d
            JOIN players p ON d.reporter_id=p.telegram_id
            JOIN matches m ON d.match_id=m.id
            WHERE d.status='open'
        """).fetchall()

def resolve_dispute(dispute_id, winner_id, resolution):
    with get_conn() as conn:
        d = conn.execute("SELECT * FROM disputes WHERE id=?", (dispute_id,)).fetchone()
        if d:
            conn.execute("UPDATE disputes SET status='resolved',resolution=?,resolved_at=? WHERE id=?",
                         (resolution, datetime.now().isoformat(), dispute_id))
            if not winner_id:
                conn.execute("UPDATE matches SET status='voided' WHERE id=?", (d["match_id"],))
        conn.commit()


# ── Torneos ───────────────────────────────────────────────────────────────────
def create_tournament(name, game_mode, prize_usd, max_wins, start_date, entry_fee=0.0):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO tournaments(name,game_mode,entry_fee,prize_usd,max_wins,start_date) VALUES(?,?,?,?,?,?)",
                  (name, game_mode, entry_fee, prize_usd, max_wins, start_date))
        conn.commit()
        return c.lastrowid

def get_active_tournaments():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM tournaments WHERE status IN ('upcoming','active') ORDER BY start_date").fetchall()


# ── Finanzas ──────────────────────────────────────────────────────────────────
def get_finance_summary():
    with get_conn() as conn:
        def period(days):
            since = (datetime.now() - timedelta(days=days)).isoformat()
            m = conn.execute("SELECT COUNT(*) FROM matches WHERE status='completed' AND ended_at>=?", (since,)).fetchone()[0]
            i = conn.execute("SELECT COALESCE(SUM(amount_usd),0) FROM payments WHERE status='approved' AND created_at>=?", (since,)).fetchone()[0]
            p = conn.execute("SELECT COALESCE(SUM(amount_usd),0) FROM transactions WHERE type='prize' AND created_at>=?", (since,)).fetchone()[0]
            w = conn.execute("SELECT COALESCE(SUM(amount_usd),0) FROM withdrawals WHERE status='approved' AND reviewed_at>=?", (since,)).fetchone()[0]
            d = conn.execute("SELECT COUNT(*) FROM disputes WHERE created_at>=?", (since,)).fetchone()[0]
            return {"matches": m, "inscriptions": round(i,2), "prizes": round(p,2),
                    "profit": round(i-p,2), "withdrawals": round(w,2),
                    "disputes": d, "dispute_rate": f"{round(d/m*100,1)}%" if m>0 else "0%"}

        t, w, mo = period(1), period(7), period(30)
        ti   = conn.execute("SELECT COALESCE(SUM(amount_usd),0) FROM payments WHERE status='approved'").fetchone()[0]
        tp   = conn.execute("SELECT COALESCE(SUM(amount_usd),0) FROM transactions WHERE type='prize'").fetchone()[0]
        to_  = conn.execute("SELECT COALESCE(SUM(amount_usd),0) FROM withdrawals WHERE status='approved'").fetchone()[0]
        pb   = conn.execute("SELECT COALESCE(SUM(balance_usd),0) FROM players").fetchone()[0]
        pp   = conn.execute("SELECT COUNT(*) FROM payments WHERE status='pending'").fetchone()[0]
        pw   = conn.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'").fetchone()[0]
        pwu  = conn.execute("SELECT COALESCE(SUM(amount_usd),0) FROM withdrawals WHERE status='pending'").fetchone()[0]
        od   = conn.execute("SELECT COUNT(*) FROM disputes WHERE status='open'").fetchone()[0]
        return {"today": t, "week": w, "month": mo,
                "total_in": round(ti,2), "total_prizes": round(tp,2),
                "total_profit": round(ti-tp,2), "total_out": round(to_,2),
                "player_balance": round(pb,2),
                "pending_payments": pp, "pending_withdrawals": pw,
                "pending_wd_usd": round(pwu,2), "in_dispute": od}


def get_stats():
    with get_conn() as conn:
        tp = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        ap = conn.execute("SELECT COUNT(*) FROM players WHERE status='active'").fetchone()[0]
        tm = conn.execute("SELECT COUNT(*) FROM matches WHERE status='completed'").fetchone()[0]
        td = conn.execute("SELECT COUNT(*) FROM matches WHERE status='completed' AND date(ended_at)=date('now')").fetchone()[0]
        wm = conn.execute("SELECT COUNT(*) FROM matches WHERE status='completed' AND ended_at>=datetime('now','-7 days')").fetchone()[0]
        mm = conn.execute("SELECT COUNT(*) FROM matches WHERE status='completed' AND ended_at>=datetime('now','-30 days')").fetchone()[0]
        qc = conn.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
        od = conn.execute("SELECT COUNT(*) FROM disputes WHERE status='open'").fetchone()[0]
        at = conn.execute("SELECT COUNT(DISTINCT player1_id)+COUNT(DISTINCT player2_id) FROM matches WHERE date(started_at)=date('now')").fetchone()[0]
        pr = conn.execute("SELECT strftime('%H',started_at) hr,COUNT(*) cnt FROM matches GROUP BY hr ORDER BY cnt DESC LIMIT 1").fetchone()
        br = conn.execute("SELECT cr_name,streak_best FROM players ORDER BY streak_best DESC LIMIT 1").fetchone()
        return {"total_players": tp, "active_players": ap,
                "total_matches": tm, "today_matches": td,
                "week_matches": wm,  "month_matches": mm,
                "queue_count": qc,   "open_disputes": od, "active_today": at,
                "peak_hour": f"{pr['hr']}:00" if pr else "N/A",
                "best_streak_player": br["cr_name"]    if br else "N/A",
                "best_streak":        br["streak_best"] if br else 0}


def get_transactions(telegram_id, limit=20):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM transactions WHERE telegram_id=? ORDER BY created_at DESC LIMIT ?",
                            (telegram_id, limit)).fetchall()
