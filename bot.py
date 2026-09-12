"""
╔══════════════════════════════════════════════════════════════╗
║                    MineVault Telegram Bot                    ║
║    Crypto Wallet · Minesweeper · Bank · Groups · Admin      ║
╚══════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import logging
import os
import random
import secrets
import sqlite3
import string
from datetime import date
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode, ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ════════════════════════════════════════════════════════
#   ★  CONFIGURATION — FILL IN BEFORE RUNNING  ★
# ════════════════════════════════════════════════════════

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Add your Telegram numeric ID(s) here
ADMIN_IDS: list[int] = [
    123456789,    # ← your ID (get it from @userinfobot)
    # 987654321,  # ← second admin
]

# ════════════════════════════════════════════════════════
#   SETTINGS
# ════════════════════════════════════════════════════════
DB_PATH    = os.getenv("DATABASE_PATH", "data/minevault.db")
START_BAL  = 500.0
MIN_BET    = 1.0
XP_PER_MSG = 2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
)
log = logging.getLogger("MineVault")

# ════════════════════════════════════════════════════════
#   UI HELPERS
# ════════════════════════════════════════════════════════

def header(title: str) -> str:
    return f"```\n{'━'*30}\n  {title}\n{'━'*30}\n```"

def divider() -> str:
    return "```\n" + "╌" * 28 + "\n```"

# ════════════════════════════════════════════════════════
#   DATABASE
# ════════════════════════════════════════════════════════

def _conn() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con

def init_db():
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id   INTEGER PRIMARY KEY,
            username      TEXT    DEFAULT '',
            first_name    TEXT    DEFAULT '',
            wallet        TEXT    UNIQUE NOT NULL,
            balance       REAL    DEFAULT 0,
            level         INTEGER DEFAULT 1,
            xp            INTEGER DEFAULT 0,
            is_banned     INTEGER DEFAULT 0,
            created_at    TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id    INTEGER,
            to_id      INTEGER,
            amount     REAL,
            kind       TEXT,
            note       TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS games (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id   INTEGER,
            board_size    INTEGER DEFAULT 5,
            mines         INTEGER DEFAULT 5,
            bet           REAL,
            status        TEXT    DEFAULT 'active',
            board         TEXT,
            revealed      TEXT    DEFAULT '[]',
            cells_open    INTEGER DEFAULT 0,
            multiplier    REAL    DEFAULT 1.0,
            potential     REAL    DEFAULT 0,
            created_at    TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS daily_stats (
            telegram_id INTEGER,
            day         TEXT,
            played      INTEGER DEFAULT 0,
            won         INTEGER DEFAULT 0,
            bet_total   REAL    DEFAULT 0,
            win_total   REAL    DEFAULT 0,
            PRIMARY KEY (telegram_id, day)
        );

        CREATE TABLE IF NOT EXISTS groups (
            chat_id    INTEGER PRIMARY KEY,
            title      TEXT,
            active     INTEGER DEFAULT 1,
            joined_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS admin_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id   INTEGER,
            action     TEXT,
            target_id  INTEGER,
            detail     TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """)
    log.info("✅  Database ready: %s", DB_PATH)

# ── DB helpers ──────────────────────────────────────────

def _wallet() -> str:
    return "MV" + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(22))

def get_user(tid: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE telegram_id=?", (tid,)).fetchone()
        return dict(row) if row else None

def upsert_user(tid: int, username: str, first_name: str) -> dict:
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE telegram_id=?", (tid,)).fetchone()
        if row:
            con.execute(
                "UPDATE users SET username=?, first_name=? WHERE telegram_id=?",
                (username, first_name, tid)
            )
        else:
            wallet = _wallet()
            con.execute(
                "INSERT INTO users (telegram_id,username,first_name,wallet,balance) VALUES (?,?,?,?,?)",
                (tid, username, first_name, wallet, START_BAL)
            )
            _log_tx(con, None, tid, START_BAL, "reward", "Welcome bonus")
        return dict(con.execute("SELECT * FROM users WHERE telegram_id=?", (tid,)).fetchone())

def is_banned(tid: int) -> bool:
    u = get_user(tid)
    return bool(u and u["is_banned"])

def add_xp(tid: int, amount: int):
    with _conn() as con:
        con.execute("UPDATE users SET xp=xp+? WHERE telegram_id=?", (amount, tid))
        u = con.execute("SELECT xp, level FROM users WHERE telegram_id=?", (tid,)).fetchone()
        if u and u["xp"] >= u["level"] * 100:
            con.execute("UPDATE users SET level=level+1 WHERE telegram_id=?", (tid,))

def _log_tx(con, from_id, to_id, amount, kind, note):
    con.execute(
        "INSERT INTO transactions (from_id,to_id,amount,kind,note) VALUES (?,?,?,?,?)",
        (from_id, to_id, amount, kind, note)
    )

def _admin_log(admin_id: int, action: str, target_id: int, detail: str):
    with _conn() as con:
        con.execute(
            "INSERT INTO admin_logs (admin_id,action,target_id,detail) VALUES (?,?,?,?)",
            (admin_id, action, target_id, detail)
        )

def get_transactions(tid: int, limit=10) -> list:
    with _conn() as con:
        rows = con.execute("""
            SELECT t.*, uf.first_name sender, ut.first_name receiver
            FROM transactions t
            LEFT JOIN users uf ON t.from_id = uf.telegram_id
            LEFT JOIN users ut ON t.to_id   = ut.telegram_id
            WHERE t.from_id=? OR t.to_id=?
            ORDER BY t.created_at DESC LIMIT ?
        """, (tid, tid, limit)).fetchall()
        return [dict(r) for r in rows]

def do_transfer(from_id: int, to_wallet: str, amount: float) -> dict:
    with _conn() as con:
        sender = con.execute("SELECT * FROM users WHERE telegram_id=?", (from_id,)).fetchone()
        if not sender:
            return {"ok": False, "err": "Sender not found"}
        if sender["balance"] < amount:
            return {"ok": False, "err": "Insufficient balance"}
        recv = con.execute("SELECT * FROM users WHERE wallet=?", (to_wallet,)).fetchone()
        if not recv:
            return {"ok": False, "err": "Wallet address not found"}
        if recv["telegram_id"] == from_id:
            return {"ok": False, "err": "You cannot send to yourself"}
        con.execute("UPDATE users SET balance=balance-? WHERE telegram_id=?", (amount, from_id))
        con.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?", (amount, recv["telegram_id"]))
        _log_tx(con, from_id, recv["telegram_id"], amount, "transfer", "P2P transfer")
        return {"ok": True, "receiver": recv["first_name"] or recv["username"], "amount": amount}

def leaderboard(limit=10) -> list:
    with _conn() as con:
        rows = con.execute(
            "SELECT first_name, username, balance, level FROM users ORDER BY balance DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_stats(tid: int) -> dict:
    with _conn() as con:
        row = con.execute("""
            SELECT SUM(played) p, SUM(won) w, SUM(bet_total) b, SUM(win_total) wn
            FROM daily_stats WHERE telegram_id=?
        """, (tid,)).fetchone()
        return {
            "played": row["p"] or 0, "won": row["w"] or 0,
            "bet": row["b"] or 0,    "win": row["wn"] or 0
        }

def get_all_users(limit=50) -> list:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

def db_global_stats() -> dict:
    with _conn() as con:
        users  = con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        banned = con.execute("SELECT COUNT(*) c FROM users WHERE is_banned=1").fetchone()["c"]
        games  = con.execute("SELECT COUNT(*) c FROM games").fetchone()["c"]
        volume = con.execute("SELECT SUM(amount) s FROM transactions WHERE kind='transfer'").fetchone()["s"] or 0
        total_coins = con.execute("SELECT SUM(balance) s FROM users").fetchone()["s"] or 0
        groups = con.execute("SELECT COUNT(*) c FROM groups WHERE active=1").fetchone()["c"]
        return {
            "users": users, "banned": banned, "games": games,
            "volume": volume, "total_coins": total_coins, "groups": groups
        }

# ── Admin DB ops ────────────────────────────────────────

def admin_ban(admin_id: int, target_id: int) -> dict:
    u = get_user(target_id)
    if not u:
        return {"ok": False, "err": "User not found"}
    if u["is_banned"]:
        return {"ok": False, "err": "Already banned"}
    with _conn() as con:
        con.execute("UPDATE users SET is_banned=1 WHERE telegram_id=?", (target_id,))
    _admin_log(admin_id, "BAN", target_id, f"Banned user {target_id}")
    return {"ok": True, "user": u}

def admin_unban(admin_id: int, target_id: int) -> dict:
    u = get_user(target_id)
    if not u:
        return {"ok": False, "err": "User not found"}
    if not u["is_banned"]:
        return {"ok": False, "err": "User is not banned"}
    with _conn() as con:
        con.execute("UPDATE users SET is_banned=0 WHERE telegram_id=?", (target_id,))
    _admin_log(admin_id, "UNBAN", target_id, f"Unbanned user {target_id}")
    return {"ok": True, "user": u}

def admin_give(admin_id: int, target_id: int, amount: float) -> dict:
    u = get_user(target_id)
    if not u:
        return {"ok": False, "err": "User not found"}
    with _conn() as con:
        con.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?", (amount, target_id))
        _log_tx(con, None, target_id, amount, "admin_give", f"Admin grant by {admin_id}")
    _admin_log(admin_id, "GIVE", target_id, f"+{amount} GEM")
    return {"ok": True, "user": u, "amount": amount}

def admin_take(admin_id: int, target_id: int, amount: float | None) -> dict:
    """amount=None means take ALL"""
    u = get_user(target_id)
    if not u:
        return {"ok": False, "err": "User not found"}
    take_amount = u["balance"] if amount is None else min(amount, u["balance"])
    with _conn() as con:
        con.execute("UPDATE users SET balance=balance-? WHERE telegram_id=?", (take_amount, target_id))
        _log_tx(con, target_id, None, take_amount, "admin_take", f"Admin deduct by {admin_id}")
    label = "ALL" if amount is None else str(amount)
    _admin_log(admin_id, "TAKE", target_id, f"-{take_amount} GEM (requested: {label})")
    return {"ok": True, "user": u, "amount": take_amount}

def admin_get_user(identifier: str) -> dict | None:
    """Find by telegram_id or @username"""
    with _conn() as con:
        if identifier.lstrip("-").isdigit():
            row = con.execute("SELECT * FROM users WHERE telegram_id=?", (int(identifier),)).fetchone()
        else:
            uname = identifier.lstrip("@")
            row = con.execute("SELECT * FROM users WHERE username=?", (uname,)).fetchone()
        return dict(row) if row else None

def admin_recent_logs(limit=15) -> list:
    with _conn() as con:
        rows = con.execute("""
            SELECT al.*, u.first_name admin_name
            FROM admin_logs al
            LEFT JOIN users u ON al.admin_id = u.telegram_id
            ORDER BY al.created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

# ════════════════════════════════════════════════════════
#   MINESWEEPER
# ════════════════════════════════════════════════════════

def _multiplier(size: int, mines: int, revealed: int) -> float:
    safe = size * size - mines
    if revealed <= 0:
        return 1.0
    prob = 1.0
    for i in range(revealed):
        prob *= (safe - i) / (size * size - i)
    if prob <= 0:
        return 1.0
    return round((1 / prob) * 0.97, 4)

def _make_board(size: int, mines: int) -> list:
    total = size * size
    pos = random.sample(range(total), min(mines, total - 1))
    return [1 if i in pos else 0 for i in range(total)]

def game_start(tid: int, size: int, mines: int, bet: float) -> dict:
    with _conn() as con:
        u = con.execute("SELECT balance FROM users WHERE telegram_id=?", (tid,)).fetchone()
        if not u or u["balance"] < bet:
            return {"ok": False, "err": "Insufficient balance"}
        active = con.execute(
            "SELECT id FROM games WHERE telegram_id=? AND status='active'", (tid,)
        ).fetchone()
        if active:
            return {"ok": False, "err": "You have an active game — /game to continue or /cashout"}
        con.execute("UPDATE users SET balance=balance-? WHERE telegram_id=?", (bet, tid))
        board = _make_board(size, mines)
        con.execute("""
            INSERT INTO games (telegram_id,board_size,mines,bet,board,potential)
            VALUES (?,?,?,?,?,?)
        """, (tid, size, mines, bet, json.dumps(board), bet))
        gid = con.execute("SELECT last_insert_rowid() r").fetchone()["r"]
        return {"ok": True, "game_id": gid, "size": size, "mines": mines, "bet": bet}

def game_reveal(tid: int, gid: int, cell: int) -> dict:
    with _conn() as con:
        g = con.execute(
            "SELECT * FROM games WHERE id=? AND telegram_id=? AND status='active'", (gid, tid)
        ).fetchone()
        if not g:
            return {"ok": False, "err": "Game not found"}
        g = dict(g)
        board    = json.loads(g["board"])
        revealed = json.loads(g["revealed"])
        if cell in revealed:
            return {"ok": False, "err": "Already revealed"}
        revealed.append(cell)
        if board[cell] == 1:
            con.execute("UPDATE games SET status='lost',revealed=? WHERE id=?",
                        (json.dumps(revealed), gid))
            _log_tx(con, tid, None, g["bet"], "game_loss", "Minesweeper loss")
            _upd_stats(con, tid, False, g["bet"], 0)
            mines_pos = [i for i, v in enumerate(board) if v == 1]
            return {"ok": True, "result": "lost", "mines": mines_pos, "bet": g["bet"]}
        cells_open = g["cells_open"] + 1
        safe_total = g["board_size"] ** 2 - g["mines"]
        mult = _multiplier(g["board_size"], g["mines"], cells_open)
        pot  = round(g["bet"] * mult, 2)
        won_all = cells_open >= safe_total
        if won_all:
            con.execute("""UPDATE games SET status='won',revealed=?,cells_open=?,
                         multiplier=?,potential=? WHERE id=?""",
                        (json.dumps(revealed), cells_open, mult, pot, gid))
            con.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?", (pot, tid))
            _log_tx(con, None, tid, pot, "game_win", "Minesweeper full clear")
            _upd_stats(con, tid, True, g["bet"], pot)
            return {"ok": True, "result": "won_all", "win": pot, "mult": mult}
        con.execute("""UPDATE games SET revealed=?,cells_open=?,multiplier=?,potential=?
                       WHERE id=?""", (json.dumps(revealed), cells_open, mult, pot, gid))
        return {"ok": True, "result": "safe", "cells_open": cells_open, "mult": mult, "pot": pot}

def game_cashout(tid: int, gid: int) -> dict:
    with _conn() as con:
        g = con.execute(
            "SELECT * FROM games WHERE id=? AND telegram_id=? AND status='active'", (gid, tid)
        ).fetchone()
        if not g:
            return {"ok": False, "err": "Game not found"}
        g = dict(g)
        if g["cells_open"] == 0:
            return {"ok": False, "err": "Open at least one cell first"}
        pot = g["potential"]
        con.execute("UPDATE games SET status='won' WHERE id=?", (gid,))
        con.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?", (pot, tid))
        _log_tx(con, None, tid, pot, "game_win", "Minesweeper cashout")
        _upd_stats(con, tid, True, g["bet"], pot)
        return {"ok": True, "win": pot, "mult": g["multiplier"]}

def get_active_game(tid: int) -> dict | None:
    with _conn() as con:
        g = con.execute(
            "SELECT * FROM games WHERE telegram_id=? AND status='active'", (tid,)
        ).fetchone()
        return dict(g) if g else None

def _upd_stats(con, tid, won, bet, win):
    today = date.today().isoformat()
    con.execute("""
        INSERT INTO daily_stats (telegram_id,day,played,won,bet_total,win_total)
        VALUES (?,?,1,?,?,?)
        ON CONFLICT(telegram_id,day) DO UPDATE SET
            played=played+1, won=won+?, bet_total=bet_total+?, win_total=win_total+?
    """, (tid, today, 1 if won else 0, bet, win, 1 if won else 0, bet, win))

# ════════════════════════════════════════════════════════
#   KEYBOARDS
# ════════════════════════════════════════════════════════

def kb_main_menu() -> object:
    b = InlineKeyboardBuilder()
    b.button(text="💎 Wallet",      callback_data="menu:wallet")
    b.button(text="🎮 Minesweeper", callback_data="menu:game")
    b.button(text="🏦 Bank",        callback_data="menu:bank")
    b.button(text="🏆 Leaderboard", callback_data="menu:lb")
    b.button(text="📊 My Stats",    callback_data="menu:stats")
    b.button(text="❓ Help",         callback_data="menu:help")
    b.adjust(2, 2, 2)
    return b.as_markup()

def kb_back(dest="main") -> object:
    b = InlineKeyboardBuilder()
    b.button(text="‹ Back", callback_data=f"menu:{dest}")
    return b.as_markup()

def kb_wallet() -> object:
    b = InlineKeyboardBuilder()
    b.button(text="💸 Send Coins",   callback_data="wallet:send")
    b.button(text="📋 Transactions", callback_data="wallet:txs")
    b.button(text="‹ Back",         callback_data="menu:main")
    b.adjust(2, 1)
    return b.as_markup()

def kb_game_setup() -> object:
    b = InlineKeyboardBuilder()
    for sz in [4, 5, 6, 7]:
        b.button(text=f"{sz}×{sz}", callback_data=f"gs:size:{sz}")
    b.button(text="── Mines ──", callback_data="gs:noop")
    for m in [3, 5, 8, 12]:
        b.button(text=f"💣 {m}", callback_data=f"gs:mines:{m}")
    b.button(text="── Bet ──", callback_data="gs:noop")
    for bet in [10, 50, 100, 500]:
        b.button(text=f"💎 {bet}", callback_data=f"gs:bet:{bet}")
    b.button(text="✅ Start Game", callback_data="gs:start")
    b.button(text="‹ Back",       callback_data="menu:main")
    b.adjust(4, 1, 4, 1, 4, 1, 1)
    return b.as_markup()

def kb_board(size: int, revealed: list) -> object:
    b = InlineKeyboardBuilder()
    revealed_set = set(revealed)
    for i in range(size * size):
        if i in revealed_set:
            b.button(text="💎", callback_data="game:noop")
        else:
            b.button(text="▪️", callback_data=f"game:reveal:{i}")
    b.adjust(size)
    return b.as_markup()

def kb_game_actions(gid: int, can_cashout: bool) -> object:
    b = InlineKeyboardBuilder()
    if can_cashout:
        b.button(text="💰 Cash Out", callback_data=f"game:cashout:{gid}")
    b.button(text="‹ Menu", callback_data="menu:main")
    b.adjust(1)
    return b.as_markup()

def kb_bank() -> object:
    b = InlineKeyboardBuilder()
    b.button(text="💳 Deposit Info", callback_data="bank:deposit")
    b.button(text="📤 Withdraw",     callback_data="bank:withdraw")
    b.button(text="📈 My Balance",   callback_data="bank:balance")
    b.button(text="‹ Back",         callback_data="menu:main")
    b.adjust(2, 1, 1)
    return b.as_markup()

# ── Admin keyboards ─────────────────────────────────────

def kb_admin_main() -> object:
    b = InlineKeyboardBuilder()
    b.button(text="👥 Users",         callback_data="adm:users")
    b.button(text="📊 Global Stats",  callback_data="adm:stats")
    b.button(text="📋 Action Logs",   callback_data="adm:logs")
    b.button(text="🔍 Lookup User",   callback_data="adm:lookup_prompt")
    b.button(text="🚫 Ban User",      callback_data="adm:ban_prompt")
    b.button(text="✅ Unban User",    callback_data="adm:unban_prompt")
    b.button(text="➕ Give Coins",    callback_data="adm:give_prompt")
    b.button(text="➖ Take Coins",    callback_data="adm:take_prompt")
    b.button(text="💥 Take ALL",      callback_data="adm:takeall_prompt")
    b.button(text="📢 Broadcast",     callback_data="adm:broadcast_prompt")
    b.adjust(2, 2, 2, 2, 1, 1)
    return b.as_markup()

def kb_admin_confirm(action: str, target: str, extra: str = "") -> object:
    data = f"adm_confirm:{action}:{target}:{extra}" if extra else f"adm_confirm:{action}:{target}:"
    b = InlineKeyboardBuilder()
    b.button(text="✅ Yes, confirm", callback_data=data)
    b.button(text="❌ Cancel",       callback_data="adm:cancel")
    b.adjust(2)
    return b.as_markup()

# ════════════════════════════════════════════════════════
#   RENDERERS
# ════════════════════════════════════════════════════════

def render_profile(u: dict) -> str:
    name   = u.get("first_name") or u.get("username") or "User"
    banned = "  🚫 **BANNED**" if u.get("is_banned") else ""
    return (
        f"{header('⚡ MineVault · Profile')}\n"
        f"👤  **{name}**{banned}\n"
        f"🆔  `@{u.get('username') or 'N/A'}`\n\n"
        f"💎  **Balance:** `{u['balance']:,.2f} GEM`\n"
        f"⭐  **Level:**   `{u['level']}`\n"
        f"🔢  **XP:**      `{u['xp']}`\n\n"
        f"```\n🏦 Wallet\n{u['wallet']}\n```\n\n"
        f"_Select an option below_"
    )

def render_wallet(u: dict) -> str:
    return (
        f"{header('💎 Wallet')}\n"
        f"**Balance:** `{u['balance']:,.2f} GEM`\n\n"
        f"```\nAddress\n{u['wallet']}\n```\n\n"
        f"_Share your address to receive coins._"
    )

def render_tx_list(txs: list, tid: int) -> str:
    if not txs:
        return f"{header('📋 Transactions')}\n_No transactions yet._"
    icons  = {"transfer": "💸", "reward": "🎁", "game_win": "🏆",
               "game_loss": "💀", "admin_give": "🎁", "admin_take": "🔻"}
    lines  = [header("📋 Last Transactions")]
    for tx in txs:
        icon  = icons.get(tx["kind"], "💳")
        going = tx["from_id"] == tid
        sign  = "−" if going else "+"
        other = (tx["receiver"] if going else tx["sender"]) or "System"
        lines.append(f"{icon}  `{sign}{tx['amount']:,.2f}` → **{other}**  _{tx['created_at'][:10]}_")
    return "\n".join(lines)

def render_stats(u: dict, s: dict) -> str:
    name  = u.get("first_name") or "Player"
    ratio = f"{s['won']}/{s['played']}" if s["played"] else "—"
    pnl   = s["win"] - s["bet"]
    sign  = "+" if pnl >= 0 else ""
    return (
        f"{header('📊 Statistics · ' + name)}\n"
        f"🎮  **Games Played:** `{s['played']}`\n"
        f"🏆  **Games Won:**   `{s['won']}`\n"
        f"📊  **W/L Ratio:**   `{ratio}`\n\n"
        f"💰  **Total Bet:**   `{s['bet']:,.2f} GEM`\n"
        f"🤑  **Total Won:**   `{s['win']:,.2f} GEM`\n"
        f"📈  **Net P&L:**     `{sign}{pnl:,.2f} GEM`\n\n"
        f"⭐  **Level:** `{u['level']}`  |  🔢 **XP:** `{u['xp']}`"
    )

def render_leaderboard(rows: list) -> str:
    medals = ["🥇", "🥈", "🥉"]
    lines  = [header("🏆 Leaderboard · Top 10")]
    for i, r in enumerate(rows):
        medal = medals[i] if i < 3 else f"`{i+1}.`"
        name  = r["first_name"] or r["username"] or "???"
        lines.append(f"{medal}  **{name}**  —  `{r['balance']:,.2f} GEM`  _(Lv.{r['level']})_")
    return "\n".join(lines)

def render_help() -> str:
    return (
        f"{header('❓ Help · Commands')}\n"
        f"**/start** — Home · Profile\n"
        f"**/wallet** — Wallet & address\n"
        f"**/send** `<addr> <amount>` — Transfer coins\n"
        f"**/play** — Start Minesweeper\n"
        f"**/game** — Resume active game\n"
        f"**/cashout** — Cash out active game\n"
        f"**/stats** — Your statistics\n"
        f"**/top** — Leaderboard\n"
        f"**/bank** — Bank panel\n"
        f"**/help** — This message\n\n"
        f"{divider()}\n"
        f"**Minesweeper:**\n"
        f"Bet → open cells → avoid mines\n"
        f"Each safe cell multiplies your reward\n"
        f"Cash out any time to lock in profit"
    )

# ── Admin renderers ─────────────────────────────────────

def render_admin_home() -> str:
    return (
        f"{header('🛡️ Admin Panel · MineVault')}\n"
        f"Select an action from the buttons below.\n\n"
        f"_All actions are logged._"
    )

def render_admin_stats() -> str:
    s = db_global_stats()
    return (
        f"{header('📊 Global Statistics')}\n"
        f"👥  **Total Users:**   `{s['users']}`\n"
        f"🚫  **Banned:**        `{s['banned']}`\n"
        f"🎮  **Games Played:**  `{s['games']}`\n"
        f"💸  **Transfer Vol:**  `{s['volume']:,.2f} GEM`\n"
        f"💎  **Coins in Circ:** `{s['total_coins']:,.2f} GEM`\n"
        f"👥  **Active Groups:** `{s['groups']}`"
    )

def render_admin_users() -> str:
    users = get_all_users(20)
    if not users:
        return f"{header('👥 Users')}\n_No users yet._"
    lines = [header(f"👥 Recent Users ({len(users)})")]
    for u in users:
        name   = (u.get("first_name") or u.get("username") or "???")[:12]
        ban    = " 🚫" if u["is_banned"] else ""
        lines.append(
            f"{'🚫' if u['is_banned'] else '👤'}  **{name}**{ban}  —  "
            f"`{u['balance']:,.0f}` GEM  |  ID: `{u['telegram_id']}`"
        )
    return "\n".join(lines)

def render_admin_logs() -> str:
    logs = admin_recent_logs(15)
    if not logs:
        return f"{header('📋 Admin Logs')}\n_No actions yet._"
    action_icons = {
        "BAN": "🚫", "UNBAN": "✅", "GIVE": "➕",
        "TAKE": "➖", "BROADCAST": "📢"
    }
    lines = [header("📋 Admin Action Logs")]
    for lg in logs:
        icon  = action_icons.get(lg["action"], "⚙️")
        admin = lg.get("admin_name") or f"#{lg['admin_id']}"
        lines.append(
            f"{icon}  **{lg['action']}** by _{admin}_  →  "
            f"`{lg['target_id']}`  _{lg['created_at'][:16]}_\n"
            f"   _{lg['detail']}_"
        )
    return "\n".join(lines)

def render_user_info(u: dict) -> str:
    ban = "🚫 **BANNED**" if u["is_banned"] else "✅ Active"
    return (
        f"{header('🔍 User Info')}\n"
        f"👤  **{u.get('first_name') or 'N/A'}** (`@{u.get('username') or 'N/A'}`)\n"
        f"🆔  `{u['telegram_id']}`\n"
        f"💎  **Balance:** `{u['balance']:,.2f} GEM`\n"
        f"⭐  **Level:** `{u['level']}`  |  🔢 **XP:** `{u['xp']}`\n"
        f"🏦  `{u['wallet']}`\n"
        f"📅  Joined: `{u['created_at'][:10]}`\n"
        f"Status: {ban}"
    )

# ════════════════════════════════════════════════════════
#   SESSION (wizard state)
# ════════════════════════════════════════════════════════

class Session:
    _d: dict = {}

    @classmethod
    def set(cls, tid, key, val):
        cls._d.setdefault(tid, {})[key] = val

    @classmethod
    def get(cls, tid, key, default=None):
        return cls._d.get(tid, {}).get(key, default)

    @classmethod
    def clear(cls, tid):
        cls._d.pop(tid, None)

# ════════════════════════════════════════════════════════
#   ROUTER
# ════════════════════════════════════════════════════════
router = Router()

# ── guard helpers ────────────────────────────────────────

def _is_admin(tid: int) -> bool:
    return tid in ADMIN_IDS

async def _check_banned(msg: Message) -> bool:
    """Returns True (and replies) if user is banned."""
    if is_banned(msg.from_user.id):
        await msg.answer(
            f"{header('🚫 Access Denied')}\n"
            f"Your account has been **banned**.\n"
            f"Contact support if you think this is a mistake.",
            parse_mode=ParseMode.MARKDOWN
        )
        return True
    return False

# ════════════════════════════════════════════════════════
#   USER COMMANDS
# ════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(msg: Message):
    if await _check_banned(msg):
        return
    u = upsert_user(msg.from_user.id, msg.from_user.username or "", msg.from_user.first_name or "")
    await msg.answer(render_profile(u), reply_markup=kb_main_menu(), parse_mode=ParseMode.MARKDOWN)

@router.message(Command("wallet"))
async def cmd_wallet(msg: Message):
    if await _check_banned(msg):
        return
    u = upsert_user(msg.from_user.id, msg.from_user.username or "", msg.from_user.first_name or "")
    await msg.answer(render_wallet(u), reply_markup=kb_wallet(), parse_mode=ParseMode.MARKDOWN)

@router.message(Command("send"))
async def cmd_send(msg: Message):
    if await _check_banned(msg):
        return
    parts = (msg.text or "").split()
    if len(parts) != 3:
        await msg.answer(
            f"{header('💸 Send Coins')}\n"
            f"Usage: `/send <wallet> <amount>`\n\n"
            f"Example:\n`/send MV1A2B3C4D5E6F7G8H9I0J12 100`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    _, to_wallet, amount_str = parts
    try:
        amount = float(amount_str)
        assert amount >= 1
    except Exception:
        await msg.answer("❌ Invalid amount. Minimum is `1 GEM`.", parse_mode=ParseMode.MARKDOWN)
        return
    if len(to_wallet) != 24 or not to_wallet.startswith("MV"):
        await msg.answer("❌ Invalid wallet address (24 chars, starts with `MV`).", parse_mode=ParseMode.MARKDOWN)
        return
    res = do_transfer(msg.from_user.id, to_wallet, amount)
    if not res["ok"]:
        await msg.answer(f"❌ **Error:** {res['err']}", parse_mode=ParseMode.MARKDOWN)
        return
    await msg.answer(
        f"```\n✅  Transfer Successful\n{'─'*28}\n```\n"
        f"💸 Sent `{amount:,.2f} GEM` to **{res['receiver']}**",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("play"))
async def cmd_play(msg: Message):
    if await _check_banned(msg):
        return
    tid = msg.from_user.id
    Session.set(tid, "game_size",  5)
    Session.set(tid, "game_mines", 5)
    Session.set(tid, "game_bet",   10)
    await msg.answer(
        f"{header('🎮 Minesweeper · Setup')}\n"
        f"Choose board size, mines and bet below.\n\n"
        f"Current: `5×5`  |  `5 mines`  |  `10 GEM`",
        reply_markup=kb_game_setup(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("game"))
async def cmd_game(msg: Message):
    if await _check_banned(msg):
        return
    g = get_active_game(msg.from_user.id)
    if not g:
        await msg.answer("No active game. Use /play to start.", parse_mode=ParseMode.MARKDOWN)
        return
    revealed = json.loads(g["revealed"])
    await msg.answer(
        f"{header('🎮 Minesweeper · Active')}\n"
        f"💣 Mines: `{g['mines']}`  |  Board: `{g['board_size']}×{g['board_size']}`\n"
        f"💎 Bet: `{g['bet']:,.2f}`  ×`{g['multiplier']:.3f}`  →  `{g['potential']:,.2f} GEM`",
        reply_markup=kb_board(g["board_size"], revealed),
        parse_mode=ParseMode.MARKDOWN
    )
    await msg.answer(
        "_Tap cells above, or cash out below._",
        reply_markup=kb_game_actions(g["id"], g["cells_open"] > 0),
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("cashout"))
async def cmd_cashout(msg: Message):
    if await _check_banned(msg):
        return
    g = get_active_game(msg.from_user.id)
    if not g:
        await msg.answer("No active game.", parse_mode=ParseMode.MARKDOWN)
        return
    res = game_cashout(msg.from_user.id, g["id"])
    if not res["ok"]:
        await msg.answer(f"❌ {res['err']}", parse_mode=ParseMode.MARKDOWN)
        return
    await msg.answer(
        f"```\n💰  Cash Out!\n{'─'*28}\n```\n"
        f"🏆 Won `{res['win']:,.2f} GEM`  (×`{res['mult']:.3f}`)",
        reply_markup=kb_main_menu(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("stats"))
async def cmd_stats(msg: Message):
    if await _check_banned(msg):
        return
    u = upsert_user(msg.from_user.id, msg.from_user.username or "", msg.from_user.first_name or "")
    s = get_stats(msg.from_user.id)
    await msg.answer(render_stats(u, s), reply_markup=kb_back(), parse_mode=ParseMode.MARKDOWN)

@router.message(Command("top"))
async def cmd_top(msg: Message):
    await msg.answer(render_leaderboard(leaderboard()), reply_markup=kb_back(), parse_mode=ParseMode.MARKDOWN)

@router.message(Command("bank"))
async def cmd_bank(msg: Message):
    if await _check_banned(msg):
        return
    u = upsert_user(msg.from_user.id, msg.from_user.username or "", msg.from_user.first_name or "")
    await msg.answer(
        f"{header('🏦 MineVault Bank')}\n"
        f"**Balance:** `{u['balance']:,.2f} GEM`\n\n_Select an option._",
        reply_markup=kb_bank(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(render_help(), reply_markup=kb_back(), parse_mode=ParseMode.MARKDOWN)

# ════════════════════════════════════════════════════════
#   ADMIN COMMANDS
# ════════════════════════════════════════════════════════

@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if not _is_admin(msg.from_user.id):
        await msg.answer("❌ Access denied.", parse_mode=ParseMode.MARKDOWN)
        return
    await msg.answer(render_admin_home(), reply_markup=kb_admin_main(), parse_mode=ParseMode.MARKDOWN)

# ── Text wizard for admin actions ────────────────────────

@router.message(F.text & F.chat.type == "private")
async def handle_text(msg: Message):
    tid     = msg.from_user.id
    waiting = Session.get(tid, "waiting")

    # ── non-admin free text ─────────────────────────────
    if not waiting:
        if is_banned(tid):
            return
        return  # ignore unknown text for regular users

    # ── admin wizard steps ──────────────────────────────
    if not _is_admin(tid):
        Session.clear(tid)
        return

    text = (msg.text or "").strip()

    # LOOKUP
    if waiting == "lookup":
        u = admin_get_user(text)
        Session.clear(tid)
        if not u:
            await msg.answer("❌ User not found.", parse_mode=ParseMode.MARKDOWN)
            return
        await msg.answer(render_user_info(u), reply_markup=kb_back("adm:cancel"), parse_mode=ParseMode.MARKDOWN)

    # BAN step 1 — get target
    elif waiting == "ban_id":
        u = admin_get_user(text)
        if not u:
            await msg.answer("❌ User not found.", parse_mode=ParseMode.MARKDOWN)
            Session.clear(tid)
            return
        Session.set(tid, "ban_target", str(u["telegram_id"]))
        Session.set(tid, "waiting", None)
        name = u.get("first_name") or u.get("username") or str(u["telegram_id"])
        await msg.answer(
            f"{header('🚫 Confirm Ban')}\n"
            f"Ban **{name}** (`{u['telegram_id']}`)?",
            reply_markup=kb_admin_confirm("ban", str(u["telegram_id"])),
            parse_mode=ParseMode.MARKDOWN
        )

    # UNBAN
    elif waiting == "unban_id":
        u = admin_get_user(text)
        if not u:
            await msg.answer("❌ User not found.", parse_mode=ParseMode.MARKDOWN)
            Session.clear(tid)
            return
        Session.set(tid, "waiting", None)
        name = u.get("first_name") or u.get("username") or str(u["telegram_id"])
        await msg.answer(
            f"{header('✅ Confirm Unban')}\n"
            f"Unban **{name}** (`{u['telegram_id']}`)?",
            reply_markup=kb_admin_confirm("unban", str(u["telegram_id"])),
            parse_mode=ParseMode.MARKDOWN
        )

    # GIVE step 1 — target
    elif waiting == "give_id":
        u = admin_get_user(text)
        if not u:
            await msg.answer("❌ User not found.", parse_mode=ParseMode.MARKDOWN)
            Session.clear(tid)
            return
        Session.set(tid, "give_target", str(u["telegram_id"]))
        Session.set(tid, "waiting", "give_amount")
        await msg.answer(
            f"How many GEM to **give** to `{u.get('first_name') or u['telegram_id']}`?\n"
            f"_(send a number)_",
            parse_mode=ParseMode.MARKDOWN
        )

    # GIVE step 2 — amount
    elif waiting == "give_amount":
        try:
            amount = float(text)
            assert amount > 0
        except Exception:
            await msg.answer("❌ Invalid amount.", parse_mode=ParseMode.MARKDOWN)
            return
        target = Session.get(tid, "give_target")
        Session.set(tid, "waiting", None)
        u = get_user(int(target))
        name = u.get("first_name") or target if u else target
        await msg.answer(
            f"{header('➕ Confirm Give')}\n"
            f"Give `{amount:,.2f} GEM` to **{name}**?",
            reply_markup=kb_admin_confirm("give", target, str(amount)),
            parse_mode=ParseMode.MARKDOWN
        )

    # TAKE step 1 — target
    elif waiting == "take_id":
        u = admin_get_user(text)
        if not u:
            await msg.answer("❌ User not found.", parse_mode=ParseMode.MARKDOWN)
            Session.clear(tid)
            return
        Session.set(tid, "take_target", str(u["telegram_id"]))
        Session.set(tid, "waiting", "take_amount")
        await msg.answer(
            f"How many GEM to **take** from `{u.get('first_name') or u['telegram_id']}`?\n"
            f"_(send a number)_",
            parse_mode=ParseMode.MARKDOWN
        )

    # TAKE step 2 — amount
    elif waiting == "take_amount":
        try:
            amount = float(text)
            assert amount > 0
        except Exception:
            await msg.answer("❌ Invalid amount.", parse_mode=ParseMode.MARKDOWN)
            return
        target = Session.get(tid, "take_target")
        Session.set(tid, "waiting", None)
        u = get_user(int(target))
        name = u.get("first_name") or target if u else target
        await msg.answer(
            f"{header('➖ Confirm Take')}\n"
            f"Take `{amount:,.2f} GEM` from **{name}**?",
            reply_markup=kb_admin_confirm("take", target, str(amount)),
            parse_mode=ParseMode.MARKDOWN
        )

    # TAKE ALL — target
    elif waiting == "takeall_id":
        u = admin_get_user(text)
        if not u:
            await msg.answer("❌ User not found.", parse_mode=ParseMode.MARKDOWN)
            Session.clear(tid)
            return
        Session.set(tid, "waiting", None)
        name = u.get("first_name") or str(u["telegram_id"])
        await msg.answer(
            f"{header('💥 Confirm Take ALL')}\n"
            f"Take **ALL** `{u['balance']:,.2f} GEM` from **{name}**?",
            reply_markup=kb_admin_confirm("takeall", str(u["telegram_id"])),
            parse_mode=ParseMode.MARKDOWN
        )

    # BROADCAST — message
    elif waiting == "broadcast_msg":
        Session.set(tid, "broadcast_text", text)
        Session.set(tid, "waiting", None)
        await msg.answer(
            f"{header('📢 Confirm Broadcast')}\n"
            f"Send this message to **all users**?\n\n"
            f"```\n{text[:300]}\n```",
            reply_markup=kb_admin_confirm("broadcast", "all", ""),
            parse_mode=ParseMode.MARKDOWN
        )

# ════════════════════════════════════════════════════════
#   CALLBACKS — USER
# ════════════════════════════════════════════════════════

async def _edit(cq: CallbackQuery, text: str, kb):
    try:
        await cq.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await cq.message.answer(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    await cq.answer()

@router.callback_query(F.data.startswith("menu:"))
async def cb_menu(cq: CallbackQuery):
    tid  = cq.from_user.id
    dest = cq.data.split(":")[1]
    u    = upsert_user(tid, cq.from_user.username or "", cq.from_user.first_name or "")

    if dest == "main":
        await _edit(cq, render_profile(u), kb_main_menu())
    elif dest == "wallet":
        await _edit(cq, render_wallet(u), kb_wallet())
    elif dest == "game":
        Session.set(tid, "game_size", 5)
        Session.set(tid, "game_mines", 5)
        Session.set(tid, "game_bet", 10)
        await _edit(cq,
            f"{header('🎮 Minesweeper · Setup')}\n"
            f"Current: `5×5`  |  `5 mines`  |  `10 GEM`",
            kb_game_setup()
        )
    elif dest == "bank":
        await _edit(cq,
            f"{header('🏦 MineVault Bank')}\n**Balance:** `{u['balance']:,.2f} GEM`",
            kb_bank()
        )
    elif dest == "lb":
        await _edit(cq, render_leaderboard(leaderboard()), kb_back())
    elif dest == "stats":
        s = get_stats(tid)
        await _edit(cq, render_stats(u, s), kb_back())
    elif dest == "help":
        await _edit(cq, render_help(), kb_back())

@router.callback_query(F.data.startswith("wallet:"))
async def cb_wallet(cq: CallbackQuery):
    act = cq.data.split(":")[1]
    if act == "send":
        await _edit(cq,
            f"{header('💸 Send Coins')}\n"
            f"Use command:\n`/send <address> <amount>`\n\n"
            f"Example:\n`/send MV1A2B3C4D... 100`",
            kb_back("wallet")
        )
    elif act == "txs":
        txs = get_transactions(cq.from_user.id)
        await _edit(cq, render_tx_list(txs, cq.from_user.id), kb_back("wallet"))

@router.callback_query(F.data.startswith("bank:"))
async def cb_bank(cq: CallbackQuery):
    u   = get_user(cq.from_user.id)
    act = cq.data.split(":")[1]
    if act == "balance":
        await _edit(cq,
            f"{header('💎 Balance')}\n```\n{u['balance']:>22,.2f} GEM\n```",
            kb_back("bank")
        )
    elif act == "deposit":
        await _edit(cq,
            f"{header('💳 Deposit')}\nSend GEM to:\n```\n{u['wallet']}\n```",
            kb_back("bank")
        )
    elif act == "withdraw":
        await _edit(cq,
            f"{header('📤 Withdraw')}\nUse: `/send <address> <amount>`",
            kb_back("bank")
        )

@router.callback_query(F.data.startswith("gs:"))
async def cb_gs(cq: CallbackQuery):
    tid  = cq.from_user.id
    _, key, *rest = cq.data.split(":")

    if key == "noop":
        await cq.answer()
        return

    if key == "size":
        Session.set(tid, "game_size", int(rest[0]))
    elif key == "mines":
        Session.set(tid, "game_mines", int(rest[0]))
    elif key == "bet":
        Session.set(tid, "game_bet", float(rest[0]))
    elif key == "start":
        size  = Session.get(tid, "game_size",  5)
        mines = Session.get(tid, "game_mines", 5)
        bet   = Session.get(tid, "game_bet",   10)
        if mines >= size * size:
            await cq.answer("⚠️ Too many mines!", show_alert=True)
            return
        res = game_start(tid, size, mines, bet)
        if not res["ok"]:
            await cq.answer(f"❌ {res['err']}", show_alert=True)
            return
        g    = get_active_game(tid)
        text = (
            f"{header('🎮 Minesweeper · Active')}\n"
            f"💣 Mines: `{mines}`  |  `{size}×{size}`\n"
            f"💎 Bet: `{bet:,.2f} GEM`  ×`1.000`  →  `{bet:,.2f} GEM`\n\n"
            f"_Tap a cell — good luck!_"
        )
        try:
            await cq.message.edit_text(text, reply_markup=kb_board(size, []), parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await cq.message.answer(text, reply_markup=kb_board(size, []), parse_mode=ParseMode.MARKDOWN)
        await cq.message.answer(
            "_Tap a cell above._",
            reply_markup=kb_game_actions(g["id"], False),
            parse_mode=ParseMode.MARKDOWN
        )
        await cq.answer("🎮 Game started!")
        return

    size  = Session.get(tid, "game_size",  5)
    mines = Session.get(tid, "game_mines", 5)
    bet   = Session.get(tid, "game_bet",   10)
    await cq.message.edit_text(
        f"{header('🎮 Minesweeper · Setup')}\n"
        f"Current: `{size}×{size}`  |  `{mines} mines`  |  `{bet:,.0f} GEM`",
        reply_markup=kb_game_setup(),
        parse_mode=ParseMode.MARKDOWN
    )
    await cq.answer(f"✔ {key} → {rest[0] if rest else ''}")

@router.callback_query(F.data.startswith("game:"))
async def cb_game(cq: CallbackQuery):
    tid   = cq.from_user.id
    parts = cq.data.split(":")
    act   = parts[1]

    if act == "noop":
        await cq.answer()
        return

    if act == "reveal":
        cell = int(parts[2])
        g    = get_active_game(tid)
        if not g:
            await cq.answer("No active game.", show_alert=True)
            return
        res = game_reveal(tid, g["id"], cell)
        if not res["ok"]:
            await cq.answer(res["err"], show_alert=True)
            return

        if res["result"] == "lost":
            b = InlineKeyboardBuilder()
            revealed_set = set(json.loads(g["revealed"]))
            revealed_set.add(cell)
            for i in range(g["board_size"] ** 2):
                if i in res["mines"]:
                    b.button(text="💣", callback_data="game:noop")
                elif i == cell:
                    b.button(text="💥", callback_data="game:noop")
                elif i in revealed_set:
                    b.button(text="💎", callback_data="game:noop")
                else:
                    b.button(text="▪️", callback_data="game:noop")
            b.adjust(g["board_size"])
            try:
                await cq.message.edit_reply_markup(reply_markup=b.as_markup())
            except Exception:
                pass
            await cq.answer("💥 BOOM! You hit a mine!", show_alert=True)
            await cq.message.answer(
                f"```\n💀  Game Over\n{'─'*28}\n```\n"
                f"Lost `{res['bet']:,.2f} GEM` — better luck next time!\n\nUse /play to retry.",
                reply_markup=kb_main_menu(),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        g = get_active_game(tid)
        revealed = json.loads(g["revealed"])

        if res["result"] == "won_all":
            b = InlineKeyboardBuilder()
            for _ in range(g["board_size"] ** 2):
                b.button(text="💎", callback_data="game:noop")
            b.adjust(g["board_size"])
            try:
                await cq.message.edit_reply_markup(reply_markup=b.as_markup())
            except Exception:
                pass
            await cq.answer(f"🏆 Full clear! +{res['win']:,.2f} GEM", show_alert=True)
            await cq.message.answer(
                f"```\n🏆  Perfect Clear!\n{'─'*28}\n```\n"
                f"💎 Won `{res['win']:,.2f} GEM`  (×`{res['mult']:.3f}`)",
                reply_markup=kb_main_menu(),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        try:
            await cq.message.edit_reply_markup(reply_markup=kb_board(g["board_size"], revealed))
        except Exception:
            pass
        await cq.answer(f"✅ Safe!  ×{res['mult']:.3f}  →  {res['pot']:,.2f} GEM")
        await cq.message.answer(
            f"💎 `{g['bet']:,.2f}`  ×`{res['mult']:.3f}`  →  `{res['pot']:,.2f} GEM`\n_Keep going or cash out._",
            reply_markup=kb_game_actions(g["id"], True),
            parse_mode=ParseMode.MARKDOWN
        )

    elif act == "cashout":
        gid = int(parts[2])
        res = game_cashout(tid, gid)
        if not res["ok"]:
            await cq.answer(res["err"], show_alert=True)
            return
        await cq.answer(f"💰 +{res['win']:,.2f} GEM", show_alert=True)
        await cq.message.answer(
            f"```\n💰  Cash Out!\n{'─'*28}\n```\n"
            f"🏆 Won `{res['win']:,.2f} GEM`  (×`{res['mult']:.3f}`)",
            reply_markup=kb_main_menu(),
            parse_mode=ParseMode.MARKDOWN
        )

@router.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(cq: CallbackQuery):
    u = upsert_user(cq.from_user.id, cq.from_user.username or "", cq.from_user.first_name or "")
    await _edit(cq, render_profile(u), kb_main_menu())
    await cq.answer("Cancelled")

# ════════════════════════════════════════════════════════
#   CALLBACKS — ADMIN
# ════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("adm:"))
async def cb_admin(cq: CallbackQuery):
    tid = cq.from_user.id
    if not _is_admin(tid):
        await cq.answer("❌ Access denied", show_alert=True)
        return

    action = cq.data.split(":")[1]

    if action == "cancel":
        Session.clear(tid)
        await _edit(cq, render_admin_home(), kb_admin_main())

    elif action == "stats":
        await _edit(cq, render_admin_stats(), kb_back("adm:cancel"))

    elif action == "users":
        await _edit(cq, render_admin_users(), kb_back("adm:cancel"))

    elif action == "logs":
        await _edit(cq, render_admin_logs(), kb_back("adm:cancel"))

    elif action == "lookup_prompt":
        Session.set(tid, "waiting", "lookup")
        await _edit(cq,
            f"{header('🔍 Lookup User')}\nSend user ID or @username:",
            kb_back("adm:cancel")
        )

    elif action == "ban_prompt":
        Session.set(tid, "waiting", "ban_id")
        await _edit(cq,
            f"{header('🚫 Ban User')}\nSend user ID or @username to ban:",
            kb_back("adm:cancel")
        )

    elif action == "unban_prompt":
        Session.set(tid, "waiting", "unban_id")
        await _edit(cq,
            f"{header('✅ Unban User')}\nSend user ID or @username to unban:",
            kb_back("adm:cancel")
        )

    elif action == "give_prompt":
        Session.set(tid, "waiting", "give_id")
        await _edit(cq,
            f"{header('➕ Give Coins')}\nSend user ID or @username:",
            kb_back("adm:cancel")
        )

    elif action == "take_prompt":
        Session.set(tid, "waiting", "take_id")
        await _edit(cq,
            f"{header('➖ Take Coins')}\nSend user ID or @username:",
            kb_back("adm:cancel")
        )

    elif action == "takeall_prompt":
        Session.set(tid, "waiting", "takeall_id")
        await _edit(cq,
            f"{header('💥 Take ALL Coins')}\nSend user ID or @username:",
            kb_back("adm:cancel")
        )

    elif action == "broadcast_prompt":
        Session.set(tid, "waiting", "broadcast_msg")
        await _edit(cq,
            f"{header('📢 Broadcast')}\nSend the message to broadcast to ALL users:",
            kb_back("adm:cancel")
        )

@router.callback_query(F.data.startswith("adm_confirm:"))
async def cb_admin_confirm(cq: CallbackQuery):
    tid = cq.from_user.id
    if not _is_admin(tid):
        await cq.answer("❌ Access denied", show_alert=True)
        return

    parts  = cq.data.split(":")  # adm_confirm:action:target:extra
    action = parts[1]
    target = parts[2]
    extra  = parts[3] if len(parts) > 3 else ""

    if action == "ban":
        res = admin_ban(tid, int(target))
        if not res["ok"]:
            await cq.answer(f"❌ {res['err']}", show_alert=True)
            return
        name = res["user"].get("first_name") or target
        await _edit(cq,
            f"```\n🚫  Done\n{'─'*28}\n```\n**{name}** has been **banned**.",
            kb_admin_main()
        )
        await cq.answer("🚫 Banned!")

    elif action == "unban":
        res = admin_unban(tid, int(target))
        if not res["ok"]:
            await cq.answer(f"❌ {res['err']}", show_alert=True)
            return
        name = res["user"].get("first_name") or target
        await _edit(cq,
            f"```\n✅  Done\n{'─'*28}\n```\n**{name}** has been **unbanned**.",
            kb_admin_main()
        )
        await cq.answer("✅ Unbanned!")

    elif action == "give":
        amount = float(extra)
        res    = admin_give(tid, int(target), amount)
        if not res["ok"]:
            await cq.answer(f"❌ {res['err']}", show_alert=True)
            return
        name = res["user"].get("first_name") or target
        await _edit(cq,
            f"```\n➕  Done\n{'─'*28}\n```\n"
            f"Gave `{amount:,.2f} GEM` to **{name}**.",
            kb_admin_main()
        )
        await cq.answer(f"✅ Gave {amount:,.2f} GEM")

    elif action == "take":
        amount = float(extra)
        res    = admin_take(tid, int(target), amount)
        if not res["ok"]:
            await cq.answer(f"❌ {res['err']}", show_alert=True)
            return
        name = res["user"].get("first_name") or target
        await _edit(cq,
            f"```\n➖  Done\n{'─'*28}\n```\n"
            f"Took `{res['amount']:,.2f} GEM` from **{name}**.",
            kb_admin_main()
        )
        await cq.answer(f"✅ Took {res['amount']:,.2f} GEM")

    elif action == "takeall":
        res = admin_take(tid, int(target), None)
        if not res["ok"]:
            await cq.answer(f"❌ {res['err']}", show_alert=True)
            return
        name = res["user"].get("first_name") or target
        await _edit(cq,
            f"```\n💥  Done\n{'─'*28}\n```\n"
            f"Took ALL `{res['amount']:,.2f} GEM` from **{name}**.",
            kb_admin_main()
        )
        await cq.answer(f"💥 Took all {res['amount']:,.2f} GEM")

    elif action == "broadcast":
        text    = Session.get(tid, "broadcast_text", "")
        Session.clear(tid)
        if not text:
            await cq.answer("❌ No message to broadcast.", show_alert=True)
            return
        users   = get_all_users(10000)
        bot     = cq.bot
        sent    = 0
        failed  = 0
        for u in users:
            try:
                await bot.send_message(
                    u["telegram_id"],
                    f"```\n📢  Announcement\n{'─'*28}\n```\n{text}",
                    parse_mode=ParseMode.MARKDOWN
                )
                sent += 1
            except Exception:
                failed += 1
        _admin_log(tid, "BROADCAST", 0, f"Sent to {sent}, failed {failed}")
        await _edit(cq,
            f"```\n📢  Broadcast Complete\n{'─'*28}\n```\n"
            f"✅ Sent: `{sent}`\n❌ Failed: `{failed}`",
            kb_admin_main()
        )
        await cq.answer(f"📢 Sent to {sent} users")

# Back button from admin sub-pages
@router.callback_query(F.data == "adm:cancel")
async def cb_adm_cancel(cq: CallbackQuery):
    if not _is_admin(cq.from_user.id):
        await cq.answer("❌ Access denied", show_alert=True)
        return
    Session.clear(cq.from_user.id)
    await _edit(cq, render_admin_home(), kb_admin_main())
    await cq.answer()

# ════════════════════════════════════════════════════════
#   GROUP HANDLER
# ════════════════════════════════════════════════════════

@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def group_msg(msg: Message):
    if not msg.from_user:
        return
    tid = msg.from_user.id
    upsert_user(tid, msg.from_user.username or "", msg.from_user.first_name or "")
    if not is_banned(tid):
        add_xp(tid, XP_PER_MSG)
    with _conn() as con:
        con.execute("""
            INSERT INTO groups (chat_id, title) VALUES (?,?)
            ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, active=1
        """, (msg.chat.id, msg.chat.title or ""))

# ════════════════════════════════════════════════════════
#   MAIN
# ════════════════════════════════════════════════════════

COMMANDS = [
    BotCommand(command="start",    description="Home · Profile"),
    BotCommand(command="wallet",   description="Wallet & address"),
    BotCommand(command="send",     description="Transfer: /send <addr> <amount>"),
    BotCommand(command="play",     description="Start Minesweeper"),
    BotCommand(command="game",     description="Resume active game"),
    BotCommand(command="cashout",  description="Cash out active game"),
    BotCommand(command="stats",    description="Your statistics"),
    BotCommand(command="top",      description="Leaderboard"),
    BotCommand(command="bank",     description="Bank panel"),
    BotCommand(command="help",     description="Help & rules"),
]

async def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        log.error("❌  Set BOT_TOKEN at the top of the file or in .env!")
        return

    if ADMIN_IDS == [123456789]:
        log.warning("⚠️  Default ADMIN_IDS detected — update them in the script!")

    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher()
    dp.include_router(router)
    await bot.set_my_commands(COMMANDS)
    log.info("🚀  MineVault Bot is online | Admins: %s", ADMIN_IDS)
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
