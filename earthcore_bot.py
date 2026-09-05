"""
╔══════════════════════════════════════════════════════════════════╗
║              🌍 EarthCore Wars — Telegram Bot                    ║
║         Solo + Group Resource War Game (Single File)            ║
║  Stack: python-telegram-bot 20.x · MongoDB · Python 3.11+       ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import asyncio
import random
import math
import logging
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

# ─────────────────────────────────────────────
# ⚙️  CONFIG
# ─────────────────────────────────────────────
BOT_TOKEN   = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
MONGO_URI   = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME     = "earthcore"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger("EarthCore")

# ─────────────────────────────────────────────
# 🎨  EMOJI PALETTE  (رنگ‌بندی دکمه‌ها)
# ─────────────────────────────────────────────
class E:
    # Actions
    MINE      = "⛏️"
    SELL      = "💰"
    UPGRADE   = "🔧"
    ATTACK    = "⚔️"
    DEFEND    = "🛡️"
    SPY       = "🕵️"
    TRADE     = "🤝"
    DONATE    = "📦"
    BACK      = "◀️"
    REFRESH   = "🔄"
    INFO      = "ℹ️"
    CONFIRM   = "✅"
    CANCEL    = "❌"
    SETTINGS  = "⚙️"
    STATS     = "📊"
    BOARD     = "🏆"
    CROWN     = "👑"
    MAP       = "🗺️"
    GROUP     = "🏰"
    PROFILE   = "🧍"

    # Resources
    STONE     = "🪨"
    IRON      = "🔩"
    CRYSTAL   = "💎"
    OIL       = "🛢️"
    PLASMA    = "⚡"
    EARTHITE  = "🌑"
    ENERGY    = "🔋"
    GOLD      = "🪙"
    SHIELD    = "🔰"

    # Layers
    L1 = "🟫"   # خاک
    L2 = "🟠"   # آتشفشانی
    L3 = "🔵"   # آبی
    L4 = "🟣"   # کوانتوم
    L5 = "❤️"   # هسته

    # Classes
    MINER     = "⛏️"
    MERCHANT  = "💼"
    ENGINEER  = "🔬"
    RAIDER    = "🗡️"
    GHOST     = "👻"

    # Status
    FIRE      = "🔥"
    ICE       = "❄️"
    STAR      = "⭐"
    WARN      = "⚠️"
    OK        = "✅"
    LOCK      = "🔒"
    UP        = "📈"
    DOWN      = "📉"

# ─────────────────────────────────────────────
# 📐  GAME CONSTANTS
# ─────────────────────────────────────────────
ENERGY_REGEN_HOURS = 3
MAX_ENERGY         = 20
BASE_ENERGY_REGEN  = 5

LAYERS = [
    {"name": "خاک",          "emoji": E.L1, "depth": (0,   100),  "min_energy": 1,  "multiplier": 1.0},
    {"name": "سنگ آتشفشانی", "emoji": E.L2, "depth": (100, 500),  "min_energy": 3,  "multiplier": 1.8},
    {"name": "لایه آبی",     "emoji": E.L3, "depth": (500, 2000), "min_energy": 5,  "multiplier": 3.2},
    {"name": "لایه کوانتوم", "emoji": E.L4, "depth": (2000,5000), "min_energy": 8,  "multiplier": 6.0},
    {"name": "هسته زمین",    "emoji": E.L5, "depth": (5000,9999), "min_energy": 15, "multiplier": 12.0},
]

RESOURCES = {
    "stone":    {"name": "سنگ",      "emoji": E.STONE,   "base_value": 1,   "layers": [0,1]},
    "iron":     {"name": "آهن",      "emoji": E.IRON,    "base_value": 3,   "layers": [0,1,2]},
    "crystal":  {"name": "کریستال",  "emoji": E.CRYSTAL, "base_value": 10,  "layers": [2,3]},
    "oil":      {"name": "نفت",      "emoji": E.OIL,     "base_value": 8,   "layers": [1,2]},
    "plasma":   {"name": "پلاسما",   "emoji": E.PLASMA,  "base_value": 50,  "layers": [3,4]},
    "earthite": {"name": "ارثیت",    "emoji": E.EARTHITE,"base_value": 500, "layers": [4]},
}

CLASSES = {
    "miner":    {"name": "حفار",     "emoji": E.MINER,    "bonus": "mine_power +50%",    "penalty": "trade_price -20%"},
    "merchant": {"name": "تاجر",     "emoji": E.MERCHANT, "bonus": "sell_price +40%",    "penalty": "mine_speed -20%"},
    "engineer": {"name": "مهندس",    "emoji": E.ENGINEER, "bonus": "upgrade_cost -30%",  "penalty": "no_attack"},
    "raider":   {"name": "غارتگر",   "emoji": E.RAIDER,   "bonus": "attack_power +60%",  "penalty": "defense -30%"},
    "ghost":    {"name": "جاسوس",    "emoji": E.GHOST,    "bonus": "spy_success +80%",   "penalty": "mine_yield -30%"},
}

UPGRADE_COSTS = {
    "drill":    [100, 300, 800, 2000, 5000],
    "storage":  [50,  150, 400, 1000, 3000],
    "shield":   [80,  200, 600, 1500, 4000],
}

UPGRADE_NAMES = {
    "drill":   f"{E.MINE} دریل حفاری",
    "storage": f"{E.STONE} انبار",
    "shield":  f"{E.SHIELD} سپر دفاعی",
}

# Conv states
(
    AWAIT_ENERGY_INPUT,
    AWAIT_DONATE_AMOUNT,
    AWAIT_TRADE_TARGET,
    AWAIT_TRADE_OFFER,
    AWAIT_ATTACK_TARGET,
    AWAIT_SPY_TARGET,
    AWAIT_GROUP_NAME,
    AWAIT_SELL_AMOUNT,
    AWAIT_NEGOTIATE_AMOUNT,
) = range(9)

# ─────────────────────────────────────────────
# 🗄️  DATABASE LAYER
# ─────────────────────────────────────────────
class DB:
    client: AsyncIOMotorClient = None
    db = None

    @classmethod
    async def connect(cls):
        cls.client = AsyncIOMotorClient(MONGO_URI)
        cls.db = cls.client[DB_NAME]
        await cls._ensure_indexes()
        log.info("✅ MongoDB connected")

    @classmethod
    async def _ensure_indexes(cls):
        await cls.db.players.create_index("user_id", unique=True)
        await cls.db.groups.create_index("group_id", unique=True)
        await cls.db.memberships.create_index([("user_id",1),("group_id",1)], unique=True)
        await cls.db.trades.create_index("created_at", expireAfterSeconds=86400)

    # ── Players ──────────────────────────────
    @classmethod
    async def get_player(cls, user_id: int) -> Optional[dict]:
        return await cls.db.players.find_one({"user_id": user_id})

    @classmethod
    async def create_player(cls, user_id: int, username: str, first_name: str, player_class: str) -> dict:
        now = datetime.utcnow()
        player = {
            "user_id":    user_id,
            "username":   username or str(user_id),
            "first_name": first_name,
            "class":      player_class,
            "level":      1,
            "xp":         0,
            "depth":      0,
            "energy":     MAX_ENERGY,
            "last_energy_regen": now,
            "inventory":  {k: 0 for k in RESOURCES},
            "gold":       50,
            "score":      0,
            "upgrades":   {"drill": 0, "storage": 0, "shield": 0},
            "group_id":   None,
            "created_at": now,
            "last_active": now,
            "stats": {
                "total_mined": 0,
                "total_attacks": 0,
                "total_spies": 0,
                "total_donated": 0,
            }
        }
        await cls.db.players.insert_one(player)
        return player

    @classmethod
    async def update_player(cls, user_id: int, update: dict):
        await cls.db.players.update_one({"user_id": user_id}, {"$set": update})

    @classmethod
    async def inc_player(cls, user_id: int, inc: dict):
        await cls.db.players.update_one({"user_id": user_id}, {"$inc": inc})

    @classmethod
    async def get_solo_leaderboard(cls, limit=10) -> list:
        cursor = cls.db.players.find({}, {"user_id":1,"first_name":1,"username":1,"score":1,"level":1,"class":1}).sort("score", -1).limit(limit)
        return await cursor.to_list(length=limit)

    # ── Groups ───────────────────────────────
    @classmethod
    async def get_group(cls, group_id: int) -> Optional[dict]:
        return await cls.db.groups.find_one({"group_id": group_id})

    @classmethod
    async def create_group(cls, group_id: int, group_name: str, owner_id: int) -> dict:
        now = datetime.utcnow()
        group = {
            "group_id":   group_id,
            "name":       group_name,
            "owner_id":   owner_id,
            "treasury":   {k: 0 for k in RESOURCES},
            "gold":       0,
            "shield_hp":  100,
            "score":      0,
            "level":      1,
            "members":    [owner_id],
            "created_at": now,
            "projects":   {},
            "alliances":  [],
            "wars":       [],
        }
        await cls.db.groups.insert_one(group)
        return group

    @classmethod
    async def update_group(cls, group_id: int, update: dict):
        await cls.db.groups.update_one({"group_id": group_id}, {"$set": update})

    @classmethod
    async def inc_group(cls, group_id: int, inc: dict):
        await cls.db.groups.update_one({"group_id": group_id}, {"$inc": inc})

    @classmethod
    async def get_group_leaderboard(cls, limit=10) -> list:
        cursor = cls.db.groups.find({}, {"group_id":1,"name":1,"score":1,"level":1,"members":1}).sort("score", -1).limit(limit)
        return await cursor.to_list(length=limit)

    # ── Trades ───────────────────────────────
    @classmethod
    async def create_trade(cls, data: dict) -> str:
        data["created_at"] = datetime.utcnow()
        data["status"] = "pending"
        r = await cls.db.trades.insert_one(data)
        return str(r.inserted_id)

    @classmethod
    async def get_trade(cls, trade_id: str) -> Optional[dict]:
        try:
            return await cls.db.trades.find_one({"_id": ObjectId(trade_id)})
        except Exception:
            return None

    @classmethod
    async def update_trade(cls, trade_id: str, update: dict):
        await cls.db.trades.update_one({"_id": ObjectId(trade_id)}, {"$set": update})


# ─────────────────────────────────────────────
# 🔧  GAME LOGIC HELPERS
# ─────────────────────────────────────────────
def get_layer_index(depth: int) -> int:
    for i, layer in enumerate(LAYERS):
        lo, hi = layer["depth"]
        if lo <= depth < hi:
            return i
    return len(LAYERS) - 1


async def regen_energy(player: dict) -> dict:
    """محاسبه انرژی تجدید‌شده و آپدیت DB"""
    now = datetime.utcnow()
    last = player.get("last_energy_regen", now)
    elapsed_hours = (now - last).total_seconds() / 3600
    regen_ticks = int(elapsed_hours / ENERGY_REGEN_HOURS)
    if regen_ticks > 0:
        regen = min(regen_ticks * BASE_ENERGY_REGEN, MAX_ENERGY - player["energy"])
        new_energy = min(player["energy"] + regen, MAX_ENERGY)
        new_time = last + timedelta(hours=regen_ticks * ENERGY_REGEN_HOURS)
        await DB.update_player(player["user_id"], {
            "energy": new_energy,
            "last_energy_regen": new_time
        })
        player["energy"] = new_energy
        player["last_energy_regen"] = new_time
    return player


def calc_mining(player: dict, energy_used: int) -> dict:
    """محاسبه نتیجه حفاری بر اساس کلاس، عمق و آپگرید"""
    layer_idx = get_layer_index(player["depth"])
    layer = LAYERS[layer_idx]
    mult  = layer["multiplier"]
    drill_bonus = 1 + (player["upgrades"]["drill"] * 0.25)

    class_bonus = 1.5 if player["class"] == "miner" else (
                  0.7 if player["class"] == "ghost" else 1.0)

    base_yield = energy_used * mult * drill_bonus * class_bonus
    depth_gain = int(energy_used * mult * drill_bonus * 3)

    # تعیین منابع
    possible_res = [k for k, v in RESOURCES.items() if layer_idx in v["layers"]]
    found = {}
    for res_key in possible_res:
        chance = 0.7 if layer_idx == 0 else (0.5 if layer_idx == 1 else 0.35)
        if res_key == "earthite":
            chance = 0.05
        if random.random() < chance:
            amount = max(1, int(random.uniform(0.5, 1.5) * base_yield /
                                RESOURCES[res_key]["base_value"]))
            found[res_key] = amount

    if not found:
        found[possible_res[0]] = max(1, int(base_yield / 2))

    xp_gain  = int(energy_used * mult * 10)
    return {"found": found, "depth_gain": depth_gain, "xp_gain": xp_gain, "layer": layer}


def calc_sell_value(player: dict, resource: str, amount: int) -> int:
    base = RESOURCES[resource]["base_value"] * amount
    merchant_bonus = 1.4 if player["class"] == "merchant" else 1.0
    return int(base * merchant_bonus)


def xp_to_next_level(level: int) -> int:
    return 100 * (level ** 2)


def check_level_up(player: dict) -> bool:
    needed = xp_to_next_level(player["level"])
    return player["xp"] >= needed


def next_energy_regen(player: dict) -> str:
    last = player.get("last_energy_regen", datetime.utcnow())
    next_t = last + timedelta(hours=ENERGY_REGEN_HOURS)
    diff = (next_t - datetime.utcnow()).total_seconds()
    if diff <= 0:
        return "همین الان!"
    m = int(diff // 60)
    s = int(diff % 60)
    return f"{m}د {s}ث"


# ─────────────────────────────────────────────
# 🎨  UI BUILDER
# ─────────────────────────────────────────────
def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def kb(*rows: list) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(list(rows))


# ── Text Builders ───────────────────────────
def render_bar(value: int, maximum: int, length: int = 10, filled="█", empty="░") -> str:
    filled_count = round(value / maximum * length) if maximum > 0 else 0
    return filled * filled_count + empty * (length - filled_count)


def player_profile_text(player: dict) -> str:
    cls     = CLASSES[player["class"]]
    layer   = LAYERS[get_layer_index(player["depth"])]
    xp_now  = player["xp"]
    xp_need = xp_to_next_level(player["level"])
    xp_bar  = render_bar(xp_now, xp_need)
    en_bar  = render_bar(player["energy"], MAX_ENERGY)
    inv     = player["inventory"]

    # فیلتر منابع غیرصفر
    res_lines = "\n".join(
        f"   {RESOURCES[k]['emoji']} {RESOURCES[k]['name']}: `{v}`"
        for k, v in inv.items() if v > 0
    ) or "   _انبار خالیه_"

    group_line = f"🏰 گروه: `{player.get('group_name', '—')}`" if player.get("group_id") else "🏰 گروه: _مستقل_"

    upgrades   = player.get("upgrades", {})
    up_drill   = upgrades.get("drill", 0)
    up_storage = upgrades.get("storage", 0)
    up_shield  = upgrades.get("shield", 0)

    return (
        f"╔═══════ {E.PROFILE} پروفایل ═══════╗\n"
        f"\n"
        f"  {cls['emoji']} *{player['first_name']}*  —  _{cls['name']}_\n"
        f"  🏅 سطح `{player['level']}`   {E.GOLD} طلا: `{player['gold']}`   {E.STAR} امتیاز: `{player['score']}`\n"
        f"\n"
        f"  {E.ENERGY} انرژی:  `{player['energy']}/{MAX_ENERGY}`\n"
        f"  [{en_bar}]\n"
        f"\n"
        f"  📊 تجربه:  `{xp_now}/{xp_need}`\n"
        f"  [{xp_bar}]\n"
        f"\n"
        f"  {layer['emoji']} عمق:   `{player['depth']}m`  —  {layer['name']}\n"
        f"\n"
        f"  ⛏ دریل: `{up_drill}/5`   📦 انبار: `{up_storage}/5`   🔰 سپر: `{up_shield}/5`\n"
        f"\n"
        f"  {group_line}\n"
        f"\n"
        f"📦 انبار:\n{res_lines}\n"
        f"\n"
        f"╚═══════════════════════════╝"
    )


def group_profile_text(group: dict) -> str:
    members_count = len(group.get("members", []))
    treasury = group.get("treasury", {})
    res_lines = "\n".join(
        f"   {RESOURCES[k]['emoji']} {RESOURCES[k]['name']}: `{v}`"
        for k, v in treasury.items() if v > 0
    ) or "   _خزانه خالیه_"
    shield_bar = render_bar(group["shield_hp"], 100)

    return (
        f"╔══════ {E.GROUP} گروه ══════╗\n"
        f"\n"
        f"  {E.CROWN} *{group['name']}*\n"
        f"  🏅 سطح `{group['level']}`   {E.STAR} امتیاز: `{group['score']}`\n"
        f"  👥 اعضا: `{members_count}`   {E.GOLD} طلا: `{group['gold']}`\n"
        f"\n"
        f"  {E.SHIELD} سپر:  `{group['shield_hp']}/100`\n"
        f"  [{shield_bar}]\n"
        f"\n"
        f"🏦 خزانه:\n{res_lines}\n"
        f"\n"
        f"╚══════════════════════════╝"
    )


# ─────────────────────────────────────────────
# 📋  KEYBOARD BUILDERS
# ─────────────────────────────────────────────
def main_menu_kb(has_group: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [btn(f"{E.MINE} حفاری",       "mine_menu"),
         btn(f"{E.SELL} بازار",        "market_menu")],
        [btn(f"{E.UPGRADE} آپگرید",    "upgrade_menu"),
         btn(f"{E.PROFILE} پروفایل",   "profile_view")],
        [btn(f"{E.ATTACK} حمله",       "attack_menu"),
         btn(f"{E.SPY} جاسوسی",        "spy_menu")],
        [btn(f"{E.BOARD} لیدربورد",    "leaderboard"),
         btn(f"{E.MAP} نقشه عمق",      "depth_map")],
    ]
    if has_group:
        rows.append([btn(f"{E.GROUP} گروه من",  "group_view"),
                     btn(f"{E.DONATE} کمک به گروه", "donate_menu")])
    else:
        rows.append([btn(f"{E.GROUP} ساخت گروه / عضویت", "group_join_menu")])
    return InlineKeyboardMarkup(rows)


def mine_menu_kb(player: dict) -> InlineKeyboardMarkup:
    layer_idx = get_layer_index(player["depth"])
    rows = []
    for i, layer in enumerate(LAYERS):
        min_e = layer["min_energy"]
        can   = player["energy"] >= min_e and i <= layer_idx + 1
        lock  = "" if can else f" {E.LOCK}"
        label = f"{layer['emoji']} {layer['name']}{lock}  (حداقل {min_e}{E.ENERGY})"
        rows.append([btn(label, f"mine_layer_{i}" if can else "mine_locked")])
    rows.append([btn(f"{E.BACK} برگشت", "main_menu")])
    return InlineKeyboardMarkup(rows)


def energy_amount_kb(player: dict, layer_idx: int) -> InlineKeyboardMarkup:
    min_e = LAYERS[layer_idx]["min_energy"]
    avail = player["energy"]
    opts  = [min_e, min(min_e * 2, avail), min(avail // 2, avail), avail]
    opts  = sorted(set(o for o in opts if min_e <= o <= avail))
    emojis = ["🟢", "🔵", "🟡", "🔴"]
    rows = []
    row = []
    for i, amt in enumerate(opts):
        em = emojis[min(i, len(emojis)-1)]
        row.append(btn(f"{em} {amt} {E.ENERGY}", f"mine_do_{layer_idx}_{amt}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([btn(f"{E.BACK} برگشت", "mine_menu")])
    return InlineKeyboardMarkup(rows)


def market_kb(player: dict) -> InlineKeyboardMarkup:
    inv = player["inventory"]
    rows = []
    for k, v in inv.items():
        if v > 0:
            price = calc_sell_value(player, k, v)
            rows.append([btn(
                f"{RESOURCES[k]['emoji']} {RESOURCES[k]['name']}  ×{v}  →  {price}{E.GOLD}",
                f"sell_{k}"
            )])
    if not rows:
        rows = [[btn("📭 انبار خالیه", "noop")]]
    rows.append([btn(f"{E.BACK} برگشت", "main_menu")])
    return InlineKeyboardMarkup(rows)


def upgrade_kb(player: dict) -> InlineKeyboardMarkup:
    ups = player.get("upgrades", {})
    rows = []
    for key, name in UPGRADE_NAMES.items():
        lvl  = ups.get(key, 0)
        costs = UPGRADE_COSTS[key]
        if lvl >= len(costs):
            rows.append([btn(f"{name}  ✨ MAX", "noop")])
        else:
            cost = costs[lvl]
            eng  = "مهندس" if player["class"] == "engineer" else None
            if eng:
                cost = int(cost * 0.7)
            can  = player["gold"] >= cost
            em   = "🟢" if can else "🔴"
            rows.append([btn(
                f"{em} {name}  Lv{lvl}→{lvl+1}  ({cost}{E.GOLD})",
                f"upgrade_{key}" if can else "upgrade_poor"
            )])
    rows.append([btn(f"{E.BACK} برگشت", "main_menu")])
    return InlineKeyboardMarkup(rows)


def leaderboard_kb() -> InlineKeyboardMarkup:
    return kb(
        [btn(f"🧍 سولو", "lb_solo"), btn(f"🏰 گروه‌ها", "lb_group")],
        [btn(f"{E.BACK} برگشت", "main_menu")]
    )


def class_select_kb() -> InlineKeyboardMarkup:
    rows = []
    for key, cls in CLASSES.items():
        rows.append([btn(f"{cls['emoji']} {cls['name']}  —  {cls['bonus']}", f"class_{key}")])
    return InlineKeyboardMarkup(rows)


def after_mine_kb(has_group: bool) -> InlineKeyboardMarkup:
    rows = [
        [btn(f"{E.MINE} حفاری دوباره", "mine_menu"),
         btn(f"{E.SELL} بفروش",         "market_menu")],
    ]
    if has_group:
        rows.append([btn(f"{E.DONATE} بده به گروه", "donate_menu")])
    rows.append([btn(f"{E.BACK} منوی اصلی", "main_menu")])
    return InlineKeyboardMarkup(rows)


def owner_group_kb(group_id: int) -> InlineKeyboardMarkup:
    return kb(
        [btn(f"{E.STATS} آمار گروه",    "group_stats"),
         btn(f"{E.TRADE} تجارت بین‌گروهی", "group_trade")],
        [btn(f"{E.ATTACK} اعلان جنگ",   "group_war"),
         btn(f"{E.TRADE} پیشنهاد اتحاد", "group_alliance")],
        [btn(f"{E.BOARD} اعضا",          "group_members"),
         btn(f"{E.BACK} برگشت",          "main_menu")]
    )


def member_group_kb() -> InlineKeyboardMarkup:
    return kb(
        [btn(f"{E.STATS} وضعیت گروه",  "group_stats"),
         btn(f"{E.DONATE} کمک به خزانه","donate_menu")],
        [btn(f"{E.BOARD} اعضا",          "group_members"),
         btn(f"{E.BACK} برگشت",          "main_menu")]
    )


# ─────────────────────────────────────────────
# 🤖  HANDLERS
# ─────────────────────────────────────────────

# ── /start ───────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    chat  = update.effective_chat
    player = await DB.get_player(user.id)

    if player:
        await _send_main_menu(update, ctx, player, edit=False)
        return

    # ثبت‌نام جدید
    text = (
        f"╔══════════════════════════╗\n"
        f"  🌍 *EarthCore Wars*\n"
        f"  به مرکز زمین خوش اومدی!\n"
        f"╚══════════════════════════╝\n\n"
        f"قبل از شروع، *کلاس* خودت رو انتخاب کن:\n\n"
        f"⛏️ *حفار* — استخراج بیشتر، فروش کمتر\n"
        f"💼 *تاجر* — فروش گرون‌تر، حفاری کندتر\n"
        f"🔬 *مهندس* — آپگرید ارزون، بدون حمله\n"
        f"🗡️ *غارتگر* — حمله قوی، دفاع ضعیف\n"
        f"👻 *جاسوس* — جاسوسی عالی، منبع کم"
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=class_select_kb()
    )


# ── Class selection ──────────────────────────
async def cb_class_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    key = q.data.split("_", 1)[1]
    user = q.from_user

    player = await DB.get_player(user.id)
    if player:
        await q.answer("قبلاً ثبت‌نام کردی!", show_alert=True)
        return

    await DB.create_player(user.id, user.username, user.first_name, key)
    cls = CLASSES[key]

    text = (
        f"✅ *{cls['emoji']} {cls['name']}* انتخاب شد!\n\n"
        f"▸ مزیت: _{cls['bonus']}_\n"
        f"▸ ضعف:  _{cls['penalty']}_\n\n"
        f"با `{MAX_ENERGY}{E.ENERGY}` انرژی و `50{E.GOLD}` طلا شروع می‌کنی.\n"
        f"موفق باشی در رسیدن به هسته! 🌑"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    player = await DB.get_player(user.id)
    await asyncio.sleep(1)
    await _send_main_menu(update, ctx, player, edit=False)


# ── Main menu callback ───────────────────────
async def cb_main_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player:
        await q.answer("اول /start بزن!", show_alert=True)
        return
    player = await regen_energy(player)
    await _send_main_menu(update, ctx, player, edit=True)


async def _send_main_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE, player: dict, edit=True):
    player = await regen_energy(player)
    has_group = bool(player.get("group_id"))
    cls = CLASSES[player["class"]]
    layer = LAYERS[get_layer_index(player["depth"])]
    next_regen = next_energy_regen(player)

    text = (
        f"╔════════ 🌍 *EarthCore Wars* ════════╗\n\n"
        f"  {cls['emoji']} *{player['first_name']}*   🏅 Lv`{player['level']}`   {E.STAR}`{player['score']}`\n"
        f"  {E.ENERGY} انرژی:  `{player['energy']}/{MAX_ENERGY}`  —  بعدی: _{next_regen}_\n"
        f"  {layer['emoji']} عمق:  `{player['depth']}m`   {E.GOLD} طلا: `{player['gold']}`\n\n"
        f"╚══════════════════════════════════════╝\n"
        f"چی میخوای انجام بدی؟"
    )

    mkup = main_menu_kb(has_group)
    if edit:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.MARKDOWN, reply_markup=mkup)
        except Exception:
            await update.callback_query.message.reply_text(
                text, parse_mode=ParseMode.MARKDOWN, reply_markup=mkup)
    else:
        msg = update.message or update.callback_query.message
        await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=mkup)


# ── Profile ──────────────────────────────────
async def cb_profile_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player:
        return
    player = await regen_energy(player)
    text = player_profile_text(player)
    await q.edit_message_text(
        text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb(
            [btn(f"{E.REFRESH} آپدیت", "profile_view")],
            [btn(f"{E.BACK} برگشت", "main_menu")]
        )
    )


# ── Mine menu ────────────────────────────────
async def cb_mine_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player:
        return
    player = await regen_energy(player)

    layer = LAYERS[get_layer_index(player["depth"])]
    text = (
        f"{E.MINE} *منوی حفاری*\n\n"
        f"  {layer['emoji']} موقعیت فعلی: `{player['depth']}m`  —  {layer['name']}\n"
        f"  {E.ENERGY} انرژی موجود: `{player['energy']}/{MAX_ENERGY}`\n\n"
        f"یه لایه برای حفاری انتخاب کن:\n"
        f"_(لایه‌های بالاتر از عمق فعلیت قفله)_"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=mine_menu_kb(player))


async def cb_mine_locked(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("🔒 این لایه قفله! عمیق‌تر حفاری کن.", show_alert=True)


async def cb_mine_layer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player:
        return
    player = await regen_energy(player)
    layer_idx = int(q.data.split("_")[-1])
    layer = LAYERS[layer_idx]

    text = (
        f"{layer['emoji']} *{layer['name']}*\n\n"
        f"  عمق: `{layer['depth'][0]}m — {layer['depth'][1]}m`\n"
        f"  ضریب منابع: `×{layer['multiplier']}`\n"
        f"  حداقل انرژی: `{layer['min_energy']}{E.ENERGY}`\n\n"
        f"  {E.ENERGY} انرژی داری: `{player['energy']}`\n\n"
        f"چقدر انرژی میذاری؟"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=energy_amount_kb(player, layer_idx))


async def cb_mine_do(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("⛏️ در حال حفاری...")
    player = await DB.get_player(q.from_user.id)
    if not player:
        return
    player = await regen_energy(player)

    parts     = q.data.split("_")
    layer_idx = int(parts[2])
    energy_used = int(parts[3])

    if player["energy"] < energy_used:
        await q.answer("انرژی کافی نداری!", show_alert=True)
        return

    result = calc_mining(player, energy_used)
    found  = result["found"]

    # آپدیت DB
    inc = {
        "energy": -energy_used,
        "depth":   result["depth_gain"],
        "xp":      result["xp_gain"],
        "score":   result["xp_gain"],
        "stats.total_mined": sum(found.values()),
    }
    for res_key, amt in found.items():
        inc[f"inventory.{res_key}"] = amt

    await DB.inc_player(player["user_id"], inc)
    player = await DB.get_player(player["user_id"])

    # Level up
    leveled_up = False
    while check_level_up(player):
        await DB.inc_player(player["user_id"], {"level": 1, "xp": -xp_to_next_level(player["level"])})
        player = await DB.get_player(player["user_id"])
        leveled_up = True

    # ساخت نتیجه
    found_lines = "\n".join(
        f"   {RESOURCES[k]['emoji']} {RESOURCES[k]['name']}: +`{v}`"
        for k, v in found.items()
    )
    layer = result["layer"]
    text = (
        f"╔═══ {layer['emoji']} نتیجه حفاری ═══╗\n\n"
        f"  ⛏️ انرژی مصرف‌شده: `{energy_used}`\n"
        f"  📍 عمق جدید: `{player['depth']}m`\n"
        f"  ⭐ تجربه: +`{result['xp_gain']}`\n\n"
        f"📦 پیدا کردی:\n{found_lines}\n\n"
    )
    if leveled_up:
        text += f"  🎉 *Level Up!* → سطح `{player['level']}`\n\n"
    text += f"╚══════════════════════════╝"

    has_group = bool(player.get("group_id"))
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=after_mine_kb(has_group))


# ── Market ───────────────────────────────────
async def cb_market_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player:
        return
    text = (
        f"{E.SELL} *بازار منابع*\n\n"
        f"یه منبع انتخاب کن تا بفروشیش:\n"
        f"_(قیمت‌ها برای کلاس تاجر ×۱.۴ میشه)_"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=market_kb(player))


async def cb_sell(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    res_key = q.data.split("_", 1)[1]
    amount  = player["inventory"].get(res_key, 0)
    if amount == 0:
        await q.answer("این منبع رو نداری!", show_alert=True)
        return

    gold = calc_sell_value(player, res_key, amount)
    await DB.update_player(player["user_id"], {f"inventory.{res_key}": 0})
    await DB.inc_player(player["user_id"], {"gold": gold, "score": gold // 5})

    res = RESOURCES[res_key]
    text = (
        f"💰 *فروش موفق!*\n\n"
        f"  {res['emoji']} {res['name']}: `{amount}` واحد\n"
        f"  💰 دریافتی: `{gold}` {E.GOLD}\n\n"
        f"  طلای فعلی: `{player['gold'] + gold}` {E.GOLD}"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=kb(
                                   [btn(f"{E.SELL} فروش بیشتر", "market_menu")],
                                   [btn(f"{E.BACK} منوی اصلی",  "main_menu")]
                               ))


# ── Upgrade ──────────────────────────────────
async def cb_upgrade_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player:
        return
    text = (
        f"{E.UPGRADE} *آپگرید تجهیزات*\n\n"
        f"  {E.GOLD} طلای فعلی: `{player['gold']}`\n\n"
        f"_مهندس‌ها ۳۰٪ تخفیف دارن_"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=upgrade_kb(player))


async def cb_upgrade_poor(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("💸 طلای کافی نداری!", show_alert=True)


async def cb_upgrade_do(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player:
        return
    key = q.data.split("_", 1)[1]
    lvl = player["upgrades"].get(key, 0)
    costs = UPGRADE_COSTS[key]
    if lvl >= len(costs):
        await q.answer("حداکثر سطح!", show_alert=True)
        return
    cost = costs[lvl]
    if player["class"] == "engineer":
        cost = int(cost * 0.7)
    if player["gold"] < cost:
        await q.answer("طلای کافی نداری!", show_alert=True)
        return

    await DB.inc_player(player["user_id"], {
        f"upgrades.{key}": 1,
        "gold": -cost
    })
    player = await DB.get_player(player["user_id"])
    name = UPGRADE_NAMES[key]
    text = (
        f"🔧 *آپگرید موفق!*\n\n"
        f"  {name}: `{lvl}` → `{lvl+1}`\n"
        f"  هزینه: `{cost}` {E.GOLD}\n"
        f"  طلای باقیمانده: `{player['gold']}` {E.GOLD}"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=kb(
                                   [btn(f"{E.UPGRADE} آپگرید بیشتر", "upgrade_menu")],
                                   [btn(f"{E.BACK} منوی اصلی",        "main_menu")]
                               ))


# ── Leaderboard ──────────────────────────────
async def cb_leaderboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        f"🏆 *لیدربورد*\n\nکدوم رو میخوای ببینی؟",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=leaderboard_kb()
    )


async def cb_lb_solo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    players = await DB.get_solo_leaderboard()
    medals  = ["🥇","🥈","🥉"] + ["🔹"] * 10
    lines   = []
    for i, p in enumerate(players):
        cls = CLASSES.get(p.get("class","miner"), {})
        em  = cls.get("emoji","⛏️")
        lines.append(
            f"{medals[i]} `{i+1}.` {em} *{p['first_name']}*  —  _{p['score']} امتیاز_"
        )
    text = "🏆 *لیدربورد سولو — هفتگی*\n\n" + "\n".join(lines)
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=kb(
                                   [btn("🏰 گروه‌ها", "lb_group")],
                                   [btn(f"{E.BACK} برگشت", "main_menu")]
                               ))


async def cb_lb_group(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    groups = await DB.get_group_leaderboard()
    medals = ["🥇","🥈","🥉"] + ["🔹"] * 10
    lines  = []
    for i, g in enumerate(groups):
        mc = len(g.get("members", []))
        lines.append(
            f"{medals[i]} `{i+1}.` 🏰 *{g['name']}*  👥`{mc}`  —  _{g['score']} امتیاز_"
        )
    if not lines:
        lines = ["_هنوز گروهی ثبت نشده_"]
    text = "🏆 *لیدربورد گروهی — هفتگی*\n\n" + "\n".join(lines)
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=kb(
                                   [btn("🧍 سولو", "lb_solo")],
                                   [btn(f"{E.BACK} برگشت", "main_menu")]
                               ))


# ── Depth map ────────────────────────────────
async def cb_depth_map(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player:
        return
    cur_idx = get_layer_index(player["depth"])
    lines   = []
    for i, layer in enumerate(LAYERS):
        arrow = " ◀ *اینجایی*" if i == cur_idx else ""
        pct   = 0
        if i == cur_idx:
            lo, hi = layer["depth"]
            pct = int((player["depth"] - lo) / (hi - lo) * 100)
        bar = render_bar(pct, 100, 8) if i == cur_idx else "░" * 8
        lines.append(
            f"  {layer['emoji']} *{layer['name']}*  `{layer['depth'][0]}—{layer['depth'][1]}m`{arrow}\n"
            f"     [{bar}] {pct}%"
        )
    text = f"🗺️ *نقشه عمق*\n\n" + "\n\n".join(lines)
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=kb([btn(f"{E.BACK} برگشت", "main_menu")]))


# ── Attack ───────────────────────────────────
async def cb_attack_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player:
        return
    if player["class"] == "engineer":
        await q.answer("🔬 مهندس‌ها نمی‌تونن حمله کنن!", show_alert=True)
        return

    # نمایش ۵ بازیکن تصادفی برای حمله
    cursor = DB.db.players.aggregate([
        {"$match": {"user_id": {"$ne": player["user_id"]}}},
        {"$sample": {"size": 5}},
        {"$project": {"user_id":1, "first_name":1, "class":1, "score":1, "upgrades":1}}
    ])
    targets = await cursor.to_list(5)
    rows    = []
    for t in targets:
        shield = t.get("upgrades", {}).get("shield", 0)
        em     = "🔴" if shield >= 3 else ("🟡" if shield >= 1 else "🟢")
        rows.append([btn(
            f"{em} {t['first_name']}  🛡{shield}  ⭐{t['score']}",
            f"attack_do_{t['user_id']}"
        )])
    rows.append([btn(f"{E.BACK} برگشت", "main_menu")])
    text = (
        f"{E.ATTACK} *انتخاب هدف*\n\n"
        f"🟢=سپر ضعیف  🟡=متوسط  🔴=قوی\n\n"
        f"۱۰{E.ENERGY} لازمه برای حمله:"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=InlineKeyboardMarkup(rows))


async def cb_attack_do(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("⚔️ در حال حمله...")
    player = await DB.get_player(q.from_user.id)
    if not player:
        return
    player = await regen_energy(player)
    if player["energy"] < 10:
        await q.answer("انرژی کافی نداری! (نیاز: 10)", show_alert=True)
        return

    target_id = int(q.data.split("_")[-1])
    target    = await DB.get_player(target_id)
    if not target:
        await q.answer("هدف پیدا نشد!", show_alert=True)
        return

    # محاسبه حمله
    attack_power  = 1.6 if player["class"] == "raider" else 1.0
    defense_power = 1.0 + target["upgrades"].get("shield", 0) * 0.2
    success_rate  = min(0.85, max(0.15, 0.5 * attack_power / defense_power))
    success       = random.random() < success_rate

    await DB.inc_player(player["user_id"], {"energy": -10, "stats.total_attacks": 1})

    if success:
        # سرقت ۲۰-۴۰٪ منابع
        stolen = {}
        for k, v in target["inventory"].items():
            if v > 0:
                amt = random.randint(max(1, v // 5), max(1, v // 2))
                stolen[k] = amt
        # آپدیت هر دو
        for k, v in stolen.items():
            await DB.inc_player(player["user_id"], {f"inventory.{k}": v})
            await DB.inc_player(target_id, {f"inventory.{k}": -min(v, target["inventory"][k])})
        gold_stolen = random.randint(0, min(30, target["gold"]))
        if gold_stolen > 0:
            await DB.inc_player(player["user_id"], {"gold": gold_stolen, "score": 50})
            await DB.inc_player(target_id, {"gold": -gold_stolen})

        stolen_text = "\n".join(
            f"   {RESOURCES[k]['emoji']} {RESOURCES[k]['name']}: +{v}"
            for k, v in stolen.items()
        ) or "   (چیزی نبود)"
        text = (
            f"⚔️ *حمله موفق!*\n\n"
            f"  🎯 هدف: *{target['first_name']}*\n"
            f"  📊 شانس موفقیت: `{int(success_rate*100)}%`\n\n"
            f"📦 غنایم:\n{stolen_text}\n"
            f"  {E.GOLD}: +`{gold_stolen}`\n\n"
            f"  +`50` امتیاز"
        )
        # اطلاع‌رسانی به قربانی
        try:
            cls = CLASSES[player["class"]]
            await ctx.bot.send_message(
                target_id,
                f"⚔️ مورد حمله قرار گرفتی!\n\n"
                f"  {cls['emoji']} *{player['first_name']}* بهت حمله کرد!\n"
                f"  سپرت رو تقویت کن! {E.SHIELD}",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass
    else:
        text = (
            f"⚔️ *حمله ناموفق!*\n\n"
            f"  🎯 هدف: *{target['first_name']}*\n"
            f"  📊 شانس موفقیت: `{int(success_rate*100)}%`\n\n"
            f"  سپر هدف خیلی قوی بود! {E.SHIELD}\n"
            f"  دریل و سطح خودت رو ارتقا بده."
        )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=kb(
                                   [btn(f"{E.ATTACK} حمله دوباره", "attack_menu")],
                                   [btn(f"{E.BACK} برگشت",         "main_menu")]
                               ))


# ── Spy ──────────────────────────────────────
async def cb_spy_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player:
        return
    cursor = DB.db.players.aggregate([
        {"$match": {"user_id": {"$ne": player["user_id"]}}},
        {"$sample": {"size": 4}},
        {"$project": {"user_id":1, "first_name":1, "class":1}}
    ])
    targets = await cursor.to_list(4)
    rows    = [[btn(f"🕵️ {t['first_name']}", f"spy_do_{t['user_id']}")] for t in targets]
    rows.append([btn(f"{E.BACK} برگشت", "main_menu")])
    text = (
        f"{E.SPY} *جاسوسی*\n\n"
        f"هزینه: `5{E.ENERGY}`\n"
        f"اطلاعات انبار هدف رو ببین!\n\n"
        f"هدف رو انتخاب کن:"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=InlineKeyboardMarkup(rows))


async def cb_spy_do(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("🕵️ در حال جاسوسی...")
    player = await DB.get_player(q.from_user.id)
    if not player:
        return
    player = await regen_energy(player)
    if player["energy"] < 5:
        await q.answer("انرژی کافی نداری! (نیاز: 5)", show_alert=True)
        return

    target_id = int(q.data.split("_")[-1])
    target    = await DB.get_player(target_id)
    if not target:
        await q.answer("هدف پیدا نشد!", show_alert=True)
        return

    success_rate = 0.8 if player["class"] == "ghost" else 0.4
    success      = random.random() < success_rate

    await DB.inc_player(player["user_id"], {"energy": -5, "stats.total_spies": 1})

    if success:
        inv   = target["inventory"]
        lines = "\n".join(
            f"  {RESOURCES[k]['emoji']} {RESOURCES[k]['name']}: `{v}`"
            for k, v in inv.items()
        )
        cls = CLASSES[target["class"]]
        text = (
            f"🕵️ *جاسوسی موفق!*\n\n"
            f"  👤 *{target['first_name']}*\n"
            f"  {cls['emoji']} کلاس: _{cls['name']}_\n"
            f"  🏅 سطح: `{target['level']}`\n"
            f"  {E.GOLD} طلا: ~`{target['gold'] // 10 * 10}` (تقریبی)\n"
            f"  📍 عمق: `{target['depth']}m`\n\n"
            f"📦 انبار هدف:\n{lines}"
        )
    else:
        text = (
            f"🕵️ *جاسوسی ناموفق!*\n\n"
            f"  هدف متوجه شد! {E.WARN}\n"
            f"  برای موفقیت بیشتر کلاس جاسوس انتخاب کن."
        )
        try:
            await ctx.bot.send_message(
                target_id,
                f"🕵️ یه جاسوس دنبالت بود!\n"
                f"ولی شناسایی شد. {E.SHIELD}",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass

    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=kb(
                                   [btn(f"{E.SPY} جاسوسی دوباره", "spy_menu")],
                                   [btn(f"{E.BACK} برگشت",         "main_menu")]
                               ))


# ── Group ─────────────────────────────────────
async def cb_group_join_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player:
        return
    if player.get("group_id"):
        await q.answer("قبلاً عضو یه گروهی!", show_alert=True)
        return
    text = (
        f"{E.GROUP} *گروه‌ها*\n\n"
        f"برای عضویت در یه گروه از ادمین اون گروه بخواه که تو رو اضافه کنه.\n\n"
        f"اگه می‌خوای *گروه جدید* بسازی، بات رو به گروه تلگرامت اضافه کن "
        f"و `/newgroup` بزن.\n\n"
        f"یا می‌تونی به صورت *مستقل (سولو)* ادامه بدی — هیچ اجباری نیست! 🧍"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=kb([btn(f"{E.BACK} برگشت", "main_menu")]))


async def cmd_newgroup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """ساخت گروه توی چت گروهی"""
    chat = update.effective_chat
    user = update.effective_user
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ این دستور فقط توی گروه کار میکنه!")
        return
    player = await DB.get_player(user.id)
    if not player:
        await update.message.reply_text("❌ اول توی DM بات /start بزن!")
        return
    existing = await DB.get_group(chat.id)
    if existing:
        await update.message.reply_text(f"🏰 این گروه قبلاً ثبت شده: *{existing['name']}*",
                                        parse_mode=ParseMode.MARKDOWN)
        return
    admins = await ctx.bot.get_chat_administrators(chat.id)
    admin_ids = [a.user.id for a in admins]
    if user.id not in admin_ids:
        await update.message.reply_text("❌ فقط ادمین‌های گروه میتونن گروه بسازن!")
        return

    group = await DB.create_group(chat.id, chat.title, user.id)
    await DB.update_player(user.id, {"group_id": chat.id, "group_name": chat.title})
    await DB.db.groups.update_one({"group_id": chat.id}, {"$addToSet": {"members": user.id}})

    text = (
        f"╔════════ 🏰 گروه ساخته شد! ════════╗\n\n"
        f"  📛 نام: *{chat.title}*\n"
        f"  👑 اونر: *{user.first_name}*\n\n"
        f"  اعضا می‌تونن /join بزنن تا عضو بشن.\n"
        f"  اونر با /groupmenu گروه رو مدیریت میکنه.\n"
        f"\n╚══════════════════════════════════╝"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """عضویت در گروه"""
    chat = update.effective_chat
    user = update.effective_user
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ این دستور فقط توی گروه کار میکنه!")
        return
    player = await DB.get_player(user.id)
    if not player:
        await update.message.reply_text("❌ اول توی DM بات /start بزن!")
        return
    if player.get("group_id"):
        await update.message.reply_text("❌ قبلاً عضو یه گروهی! اول /leave بزن.")
        return
    group = await DB.get_group(chat.id)
    if not group:
        await update.message.reply_text("❌ این گروه ثبت نشده. ادمین باید /newgroup بزنه.")
        return

    await DB.update_player(user.id, {"group_id": chat.id, "group_name": chat.title})
    await DB.db.groups.update_one({"group_id": chat.id}, {"$addToSet": {"members": user.id}})
    await update.message.reply_text(
        f"✅ *{user.first_name}* به گروه *{group['name']}* پیوست! {E.GROUP}",
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_leave(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """خروج از گروه"""
    user = update.effective_user
    player = await DB.get_player(user.id)
    if not player or not player.get("group_id"):
        await update.message.reply_text("عضو هیچ گروهی نیستی!")
        return
    gid = player["group_id"]
    await DB.db.groups.update_one({"group_id": gid}, {"$pull": {"members": user.id}})
    await DB.update_player(user.id, {"group_id": None, "group_name": None})
    await update.message.reply_text(f"✅ از گروه خارج شدی. {E.PROFILE} الان مستقلی!")


async def cb_group_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player or not player.get("group_id"):
        await q.answer("عضو گروهی نیستی!", show_alert=True)
        return
    group = await DB.get_group(player["group_id"])
    if not group:
        await q.answer("گروه پیدا نشد!", show_alert=True)
        return
    text = group_profile_text(group)
    is_owner = group["owner_id"] == q.from_user.id
    mkup = owner_group_kb(group["group_id"]) if is_owner else member_group_kb()
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=mkup)


async def cb_group_members(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player or not player.get("group_id"):
        return
    group = await DB.get_group(player["group_id"])
    if not group:
        return

    member_ids = group.get("members", [])
    cursor = DB.db.players.find(
        {"user_id": {"$in": member_ids}},
        {"user_id":1,"first_name":1,"class":1,"score":1,"level":1}
    ).sort("score", -1)
    members = await cursor.to_list(20)

    lines = []
    for m in members:
        cls   = CLASSES.get(m.get("class","miner"),{})
        crown = "👑 " if m["user_id"] == group["owner_id"] else ""
        lines.append(f"  {crown}{cls.get('emoji','⛏️')} *{m['first_name']}*  Lv`{m['level']}`  ⭐`{m['score']}`")

    text = f"👥 *اعضای {group['name']}*\n\n" + "\n".join(lines)
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=kb([btn(f"{E.BACK} برگشت", "group_view")]))


async def cb_group_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player or not player.get("group_id"):
        return
    group = await DB.get_group(player["group_id"])
    if not group:
        return
    text = group_profile_text(group)
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=kb([btn(f"{E.BACK} برگشت", "group_view")]))


# ── Donate ───────────────────────────────────
async def cb_donate_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player or not player.get("group_id"):
        await q.answer("عضو گروهی نیستی!", show_alert=True)
        return

    inv  = player["inventory"]
    rows = []
    for k, v in inv.items():
        if v > 0:
            rows.append([btn(
                f"{RESOURCES[k]['emoji']} {RESOURCES[k]['name']}  ×{v}",
                f"donate_{k}"
            )])
    if not rows:
        rows = [[btn("📭 انبار خالیه", "noop")]]
    rows.append([btn(f"{E.BACK} برگشت", "main_menu")])
    text = (
        f"{E.DONATE} *کمک به خزانه گروه*\n\n"
        f"کدوم منبع رو میخوای بدی؟"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=InlineKeyboardMarkup(rows))


async def cb_donate_resource(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player or not player.get("group_id"):
        return
    res_key = q.data.split("_", 1)[1]
    amount  = player["inventory"].get(res_key, 0)
    if amount == 0:
        await q.answer("این منبع رو نداری!", show_alert=True)
        return

    # انتقال کل مقدار به خزانه
    await DB.update_player(player["user_id"], {f"inventory.{res_key}": 0})
    await DB.inc_group(player["group_id"], {f"treasury.{res_key}": amount})
    await DB.inc_player(player["user_id"], {"stats.total_donated": amount, "score": amount * 2})

    res = RESOURCES[res_key]
    text = (
        f"{E.DONATE} *کمک موفق!*\n\n"
        f"  {res['emoji']} {res['name']}: `{amount}` واحد → خزانه گروه\n"
        f"  +`{amount * 2}` امتیاز برات ثبت شد {E.STAR}"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=kb(
                                   [btn(f"{E.DONATE} کمک بیشتر", "donate_menu")],
                                   [btn(f"{E.BACK} منوی اصلی",   "main_menu")]
                               ))


# ── Group trade (owner only) ──────────────────
async def cb_group_trade(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    player = await DB.get_player(q.from_user.id)
    if not player or not player.get("group_id"):
        return
    group = await DB.get_group(player["group_id"])
    if not group or group["owner_id"] != q.from_user.id:
        await q.answer("فقط اونر میتونه تجارت بین‌گروهی انجام بده!", show_alert=True)
        return

    # نمایش گروه‌های دیگه
    cursor = DB.db.groups.find(
        {"group_id": {"$ne": group["group_id"]}},
        {"group_id":1,"name":1,"score":1}
    ).sort("score", -1).limit(5)
    groups = await cursor.to_list(5)
    rows   = [[btn(f"🏰 {g['name']}  ⭐{g['score']}", f"gtrade_{g['group_id']}")] for g in groups]
    if not rows:
        rows = [[btn("🏚 هنوز گروه دیگه‌ای نیست", "noop")]]
    rows.append([btn(f"{E.BACK} برگشت", "group_view")])
    text = (
        f"{E.TRADE} *تجارت بین‌گروهی*\n\n"
        f"خزانه گروه شما:\n"
        + "\n".join(
            f"  {RESOURCES[k]['emoji']} {v}"
            for k, v in group["treasury"].items() if v > 0
        ) + "\n\nگروه مقصد:"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=InlineKeyboardMarkup(rows))


async def cb_gtrade(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target_group_id = int(q.data.split("_")[1])
    player = await DB.get_player(q.from_user.id)
    if not player:
        return
    my_group     = await DB.get_group(player["group_id"])
    target_group = await DB.get_group(target_group_id)
    if not target_group:
        return

    text = (
        f"{E.TRADE} *پیشنهاد تجارت*\n\n"
        f"از: 🏰 *{my_group['name']}*\n"
        f"به: 🏰 *{target_group['name']}*\n\n"
        f"۵۰ آهن می‌فرستی، ۲۰ کریستال می‌گیری — مثال.\n\n"
        f"پیشنهاد تجاریت رو توی چت گروه خودت بنویس:\n"
        f"`/offer [target_group_id] [منبع ارسال] [مقدار] [منبع دریافت] [مقدار]`\n\n"
        f"مثال:\n`/offer {target_group_id} iron 50 crystal 20`"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=kb([btn(f"{E.BACK} برگشت", "group_view")]))


async def cmd_offer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/offer [target_gid] [res_out] [amt_out] [res_in] [amt_in]"""
    user  = update.effective_user
    chat  = update.effective_chat
    args  = ctx.args
    if not args or len(args) < 5:
        await update.message.reply_text(
            "📋 فرمت:\n`/offer [گروه_هدف] [منبع_شما] [مقدار] [منبع_مقابل] [مقدار]`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    player = await DB.get_player(user.id)
    if not player or not player.get("group_id"):
        await update.message.reply_text("❌ عضو گروهی نیستی!")
        return
    my_group = await DB.get_group(player["group_id"])
    if not my_group or my_group["owner_id"] != user.id:
        await update.message.reply_text("❌ فقط اونر می‌تونه پیشنهاد بده!")
        return

    try:
        tgid    = int(args[0])
        res_out = args[1].lower()
        amt_out = int(args[2])
        res_in  = args[3].lower()
        amt_in  = int(args[4])
    except (ValueError, IndexError):
        await update.message.reply_text("❌ فرمت اشتباهه!")
        return

    if res_out not in RESOURCES or res_in not in RESOURCES:
        await update.message.reply_text(
            f"❌ منابع معتبر: {', '.join(RESOURCES.keys())}"
        )
        return

    if my_group["treasury"].get(res_out, 0) < amt_out:
        await update.message.reply_text("❌ خزانه کافی نداری!")
        return

    target_group = await DB.get_group(tgid)
    if not target_group:
        await update.message.reply_text("❌ گروه هدف پیدا نشد!")
        return

    trade_id = await DB.create_trade({
        "from_group": player["group_id"],
        "to_group":   tgid,
        "res_out":    res_out,
        "amt_out":    amt_out,
        "res_in":     res_in,
        "amt_in":     amt_in,
        "owner_id":   user.id,
    })

    out_r = RESOURCES[res_out]
    in_r  = RESOURCES[res_in]
    text  = (
        f"{E.TRADE} *پیشنهاد تجاری*\n\n"
        f"از: 🏰 *{my_group['name']}*\n"
        f"به: 🏰 *{target_group['name']}*\n\n"
        f"  {out_r['emoji']} {out_r['name']}: `-{amt_out}` (ارسال)\n"
        f"  {in_r['emoji']} {in_r['name']}: `+{amt_in}` (دریافت)"
    )
    mkup = kb(
        [btn(f"✅ قبول",          f"trade_accept_{trade_id}"),
         btn(f"❌ رد",             f"trade_reject_{trade_id}")],
        [btn(f"🔄 مذاکره",        f"trade_negotiate_{trade_id}")]
    )
    try:
        await ctx.bot.send_message(tgid, text,
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=mkup)
        await update.message.reply_text("✅ پیشنهاد تجاری ارسال شد!")
    except Exception:
        await update.message.reply_text(
            "✅ پیشنهاد ثبت شد.\n"
            f"ID: `{trade_id}`\n"
            f"اونر گروه هدف باید /accept `{trade_id}` بزنه.",
            parse_mode=ParseMode.MARKDOWN
        )


async def cb_trade_accept(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    trade_id = q.data.split("_")[-1]
    trade    = await DB.get_trade(trade_id)
    if not trade or trade["status"] != "pending":
        await q.answer("این پیشنهاد دیگه معتبر نیست!", show_alert=True)
        return

    player = await DB.get_player(q.from_user.id)
    if not player:
        return
    to_group = await DB.get_group(trade["to_group"])
    if not to_group or to_group["owner_id"] != q.from_user.id:
        await q.answer("فقط اونر گروه مقصد می‌تونه قبول کنه!", show_alert=True)
        return

    fg = await DB.get_group(trade["from_group"])
    if not fg:
        return

    # بررسی موجودی هر دو طرف
    if fg["treasury"].get(trade["res_out"], 0) < trade["amt_out"]:
        await q.answer("خزانه گروه فرستنده کافی نیست!", show_alert=True)
        return
    if to_group["treasury"].get(trade["res_in"], 0) < trade["amt_in"]:
        await q.answer("خزانه گروه شما کافی نیست!", show_alert=True)
        return

    # انجام معامله
    await DB.inc_group(trade["from_group"], {
        f"treasury.{trade['res_out']}": -trade["amt_out"],
        f"treasury.{trade['res_in']}":   trade["amt_in"],
        "score": 100
    })
    await DB.inc_group(trade["to_group"], {
        f"treasury.{trade['res_in']}":   -trade["amt_in"],
        f"treasury.{trade['res_out']}":   trade["amt_out"],
        "score": 100
    })
    await DB.update_trade(trade_id, {"status": "completed"})

    out_r = RESOURCES[trade["res_out"]]
    in_r  = RESOURCES[trade["res_in"]]
    text  = (
        f"✅ *تجارت انجام شد!*\n\n"
        f"🏰 *{fg['name']}* ↔ 🏰 *{to_group['name']}*\n\n"
        f"  {out_r['emoji']} {trade['amt_out']} {out_r['name']}\n"
        f"  ↕️\n"
        f"  {in_r['emoji']} {trade['amt_in']} {in_r['name']}\n\n"
        f"هر دو گروه +`100` امتیاز گرفتن!"
    )
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    try:
        await ctx.bot.send_message(trade["from_group"], text, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        pass


async def cb_trade_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    trade_id = q.data.split("_")[-1]
    await DB.update_trade(trade_id, {"status": "rejected"})
    await q.edit_message_text("❌ پیشنهاد تجاری رد شد.")


# ── Noop ─────────────────────────────────────
async def cb_noop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()


# ── /me command ──────────────────────────────
async def cmd_me(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user   = update.effective_user
    player = await DB.get_player(user.id)
    if not player:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    player = await regen_energy(player)
    text   = player_profile_text(player)
    has_group = bool(player.get("group_id"))
    await update.message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_kb(has_group)
    )


# ── /mine command (quick) ────────────────────
async def cmd_mine_quick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user   = update.effective_user
    player = await DB.get_player(user.id)
    if not player:
        await update.message.reply_text("❌ اول /start بزن!")
        return
    player = await regen_energy(player)
    if player["energy"] < 1:
        nxt = next_energy_regen(player)
        await update.message.reply_text(
            f"⚡ انرژی نداری! بعدی در `{nxt}`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    layer_idx = get_layer_index(player["depth"])
    text = (
        f"{E.MINE} *حفاری سریع*\n\n"
        f"  {E.ENERGY} انرژی: `{player['energy']}/{MAX_ENERGY}`\n\n"
        f"چقدر انرژی میذاری؟"
    )
    await update.message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=energy_amount_kb(player, layer_idx)
    )


# ── /groupmenu command ───────────────────────
async def cmd_groupmenu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    chat  = update.effective_chat
    player = await DB.get_player(user.id)
    if not player or not player.get("group_id"):
        await update.message.reply_text("❌ عضو گروهی نیستی!")
        return
    group = await DB.get_group(player["group_id"])
    if not group:
        return
    text = group_profile_text(group)
    is_owner = group["owner_id"] == user.id
    mkup = owner_group_kb(group["group_id"]) if is_owner else member_group_kb()
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=mkup)


# ─────────────────────────────────────────────
# 🔁  CALLBACK ROUTER
# ─────────────────────────────────────────────
CALLBACK_MAP = {
    "main_menu":       cb_main_menu,
    "profile_view":    cb_profile_view,
    "mine_menu":       cb_mine_menu,
    "mine_locked":     cb_mine_locked,
    "market_menu":     cb_market_menu,
    "upgrade_menu":    cb_upgrade_menu,
    "upgrade_poor":    cb_upgrade_poor,
    "leaderboard":     cb_leaderboard,
    "lb_solo":         cb_lb_solo,
    "lb_group":        cb_lb_group,
    "depth_map":       cb_depth_map,
    "attack_menu":     cb_attack_menu,
    "spy_menu":        cb_spy_menu,
    "group_join_menu": cb_group_join_menu,
    "group_view":      cb_group_view,
    "group_members":   cb_group_members,
    "group_stats":     cb_group_stats,
    "group_trade":     cb_group_trade,
    "donate_menu":     cb_donate_menu,
    "noop":            cb_noop,
}


async def route_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data

    # exact match
    if data in CALLBACK_MAP:
        return await CALLBACK_MAP[data](update, ctx)

    # prefix match
    if data.startswith("mine_layer_"):   return await cb_mine_layer(update, ctx)
    if data.startswith("mine_do_"):      return await cb_mine_do(update, ctx)
    if data.startswith("class_"):        return await cb_class_select(update, ctx)
    if data.startswith("sell_"):         return await cb_sell(update, ctx)
    if data.startswith("upgrade_"):      return await cb_upgrade_do(update, ctx)
    if data.startswith("attack_do_"):    return await cb_attack_do(update, ctx)
    if data.startswith("spy_do_"):       return await cb_spy_do(update, ctx)
    if data.startswith("donate_"):       return await cb_donate_resource(update, ctx)
    if data.startswith("gtrade_"):       return await cb_gtrade(update, ctx)
    if data.startswith("trade_accept_"): return await cb_trade_accept(update, ctx)
    if data.startswith("trade_reject_"): return await cb_trade_reject(update, ctx)
    if data.startswith("group_war"):     await update.callback_query.answer("⚔️ بزودی!", show_alert=True)
    if data.startswith("group_alliance"):await update.callback_query.answer("🤝 بزودی!", show_alert=True)

    log.warning(f"Unhandled callback: {data}")


# ─────────────────────────────────────────────
# 🌟  MAIN
# ─────────────────────────────────────────────
async def post_init(app):
    await DB.connect()
    await app.bot.set_my_commands([
        BotCommand("start",     "شروع بازی / منوی اصلی"),
        BotCommand("me",        "پروفایل شخصی"),
        BotCommand("mine",      "حفاری سریع"),
        BotCommand("groupmenu", "مدیریت گروه"),
        BotCommand("newgroup",  "ثبت گروه تلگرامی (توی گروه)"),
        BotCommand("join",      "عضویت در گروه (توی گروه)"),
        BotCommand("leave",     "خروج از گروه"),
        BotCommand("offer",     "پیشنهاد تجاری بین‌گروهی"),
    ])
    log.info("✅ Bot initialized")


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Commands
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("me",        cmd_me))
    app.add_handler(CommandHandler("mine",      cmd_mine_quick))
    app.add_handler(CommandHandler("groupmenu", cmd_groupmenu))
    app.add_handler(CommandHandler("newgroup",  cmd_newgroup))
    app.add_handler(CommandHandler("join",      cmd_join))
    app.add_handler(CommandHandler("leave",     cmd_leave))
    app.add_handler(CommandHandler("offer",     cmd_offer))

    # All callbacks via single router
    app.add_handler(CallbackQueryHandler(route_callback))

    log.info("🚀 EarthCore Wars bot started!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
