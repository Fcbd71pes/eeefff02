# db.py - Termux Compatible Version (Enhanced)
import sqlite3
import time
import asyncio
import logging
from datetime import datetime
import uuid
import config
import threading
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)
_conn = None
_thread_lock = threading.Lock()
_async_lock = None

def get_conn():
    """Termux সামঞ্জস্যপূর্ণ ডাটাবেস সংযোগ (উন্নত)"""
    global _conn
    if _conn is None:
        with _thread_lock:
            if _conn is None:
                try:
                    _conn = sqlite3.connect(
                        config.LOCAL_DB,
                        check_same_thread=False,
                        timeout=config.DB_TIMEOUT,
                        isolation_level=None  # Autocommit mode
                    )
                    _conn.row_factory = sqlite3.Row
                    # WAL mode for better concurrency
                    try:
                        _conn.execute("PRAGMA journal_mode=WAL")
                        _conn.execute("PRAGMA synchronous=NORMAL")
                        _conn.execute(f"PRAGMA busy_timeout={int(config.DB_TIMEOUT * 1000)}")
                    except:
                        pass  # Some Termux devices may not support WAL
                    logger.info(f"Database connected: {config.LOCAL_DB}")
                except Exception as e:
                    logger.error(f"Database connection failed: {e}")
                    raise
    return _conn

def init_db():
    """ডাটাবেস টেবিল সৃষ্টি"""
    try:
        conn = get_conn()
        c = conn.cursor()

        # টেবিল তৈরি
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id INTEGER PRIMARY KEY, ingame_name TEXT, phone_number TEXT,
                      is_registered INTEGER DEFAULT 0, balance REAL DEFAULT 0,
                      welcome_given INTEGER DEFAULT 0, wins INTEGER DEFAULT 0,
                      losses INTEGER DEFAULT 0, created_at TIMESTAMP, state TEXT,
                      state_data TEXT, referrer_id INTEGER, elo_rating INTEGER DEFAULT 1000,
                      is_banned INTEGER DEFAULT 0)''')

        c.execute('''CREATE TABLE IF NOT EXISTS deposit_requests
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, txid TEXT,
                      amount REAL, status TEXT DEFAULT "pending", created_at INTEGER)''')

        c.execute('''CREATE TABLE IF NOT EXISTS withdrawal_requests
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL,
                      method TEXT, account_number TEXT, status TEXT DEFAULT "pending",
                      created_at INTEGER)''')

        c.execute('''CREATE TABLE IF NOT EXISTS transactions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL,
                      type TEXT, note TEXT, created_at INTEGER)''')

        c.execute('''CREATE TABLE IF NOT EXISTS matchmaking_queue
                     (user_id INTEGER PRIMARY KEY, fee REAL, joined_at INTEGER,
                      lobby_message_id INTEGER)''')

        c.execute('''CREATE TABLE IF NOT EXISTS active_matches
                     (match_id TEXT PRIMARY KEY, player1_id INTEGER, player2_id INTEGER,
                      fee REAL, status TEXT, room_code TEXT, created_at INTEGER,
                      p1_screenshot_id TEXT, p2_screenshot_id TEXT, winner_id INTEGER)''')

        c.execute('''CREATE TABLE IF NOT EXISTS settings
                     (key TEXT PRIMARY KEY, value TEXT)''')

        # নতুন কলাম যোগ করা (নিরাপদ)
        try:
            c.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        try:
            c.execute("ALTER TABLE users ADD COLUMN elo_rating INTEGER DEFAULT 1000")
        except sqlite3.OperationalError:
            pass

        # ইন্ডেক্স তৈরি (পারফরমেন্স বৃদ্ধি)
        try:
            c.execute("CREATE INDEX IF NOT EXISTS idx_user_registered ON users(is_registered)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_match_status ON active_matches(status)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_queue_fee ON matchmaking_queue(fee)")
        except sqlite3.OperationalError:
            pass

        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise

# --- Async Helper ---
async def run_db(func, *args):
    """Asyncio সাথে ডাটাবেস অপারেশন চালানো"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args))

# --- Settings ---
def get_setting_sync(key: str) -> Optional[str]:
    try:
        c = get_conn().cursor()
        c.execute("SELECT value FROM settings WHERE key=?", (key,))
        r = c.fetchone()
        return r['value'] if r else None
    except Exception as e:
        logger.error(f"get_setting_sync error: {e}")
        return None

async def get_setting(key: str) -> Optional[str]:
    return await run_db(get_setting_sync, key)

def set_setting_sync(key: str, value: str) -> None:
    try:
        c = get_conn().cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        get_conn().commit()
    except Exception as e:
        logger.error(f"set_setting_sync error: {e}")

async def set_setting(key: str, v: str) -> None:
    await run_db(set_setting_sync, key, v)

# --- User Functions ---
def get_user_sync(uid: int) -> Optional[Dict[str, Any]]:
    try:
        c = get_conn().cursor()
        c.execute('SELECT * FROM users WHERE user_id=?', (uid,))
        r = c.fetchone()
        return dict(r) if r else None
    except Exception as e:
        logger.error(f"get_user_sync error: {e}")
        return None

async def get_user(uid: int) -> Optional[Dict[str, Any]]:
    return await run_db(get_user_sync, uid)

def create_user_sync(uid: int, name: str, ref: Optional[int]) -> None:
    try:
        c = get_conn().cursor()
        c.execute('INSERT OR IGNORE INTO users(user_id, ingame_name, created_at) VALUES(?,?,?)',
                 (uid, name, datetime.now()))
        if ref:
            c.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (ref, uid))
        get_conn().commit()
    except Exception as e:
        logger.error(f"create_user_sync error: {e}")

async def create_user_if_not_exists(u: int, n: str, r: Optional[int]) -> None:
    await run_db(create_user_sync, u, n, r)

def update_user_fields_sync(uid: int, data: Dict[str, Any]) -> None:
    try:
        c = get_conn().cursor()
        sets = ','.join([f"{k}=?" for k in data.keys()])
        params = list(data.values()) + [uid]
        c.execute(f'UPDATE users SET {sets} WHERE user_id=?', params)
        get_conn().commit()
    except Exception as e:
        logger.error(f"update_user_fields_sync error: {e}")

async def update_user_fields(uid: int, data: Dict[str, Any]) -> None:
    await run_db(update_user_fields_sync, uid, data)

async def set_user_state(uid: int, s: Optional[str], d: Optional[str] = None) -> None:
    await update_user_fields(uid, {'state': s, 'state_data': d})

def adjust_balance_sync(uid: int, amt: float, type: str, note: str = '') -> None:
    try:
        c = get_conn().cursor()
        c.execute('UPDATE users SET balance=balance+? WHERE user_id=?', (amt, uid))
        c.execute('INSERT INTO transactions(user_id, amount, type, note, created_at) VALUES(?,?,?,?,?)',
                 (uid, amt, type, note, int(time.time())))
        get_conn().commit()
    except Exception as e:
        logger.error(f"adjust_balance_sync error: {e}")

async def adjust_balance(uid: int, amt: float, type: str, note: str = '') -> None:
    await run_db(adjust_balance_sync, uid, amt, type, note)

# --- Matchmaking ---
def find_opp_sync(fee: float, exc_uid: int) -> Optional[Dict[str, Any]]:
    try:
        c = get_conn().cursor()
        c.execute('SELECT * FROM matchmaking_queue WHERE fee = ? AND user_id != ? LIMIT 1',
                 (fee, exc_uid))
        r = c.fetchone()
        return dict(r) if r else None
    except Exception as e:
        logger.error(f"find_opp_sync error: {e}")
        return None

async def find_opponent_in_queue(f: float, e: int) -> Optional[Dict[str, Any]]:
    return await run_db(find_opp_sync, f, e)

def add_queue_sync(uid: int, fee: float, mid: int) -> None:
    try:
        c = get_conn().cursor()
        c.execute('INSERT OR REPLACE INTO matchmaking_queue(user_id,fee,joined_at,lobby_message_id) VALUES(?,?,?,?)',
                 (uid, fee, int(time.time()), mid))
        get_conn().commit()
    except Exception as e:
        logger.error(f"add_queue_sync error: {e}")

async def add_to_queue(u: int, f: float, m: int) -> None:
    await run_db(add_queue_sync, u, f, m)

def rem_queue_sync(uid: int) -> None:
    try:
        c = get_conn().cursor()
        c.execute('DELETE FROM matchmaking_queue WHERE user_id=?', (uid,))
        get_conn().commit()
    except Exception as e:
        logger.error(f"rem_queue_sync error: {e}")

async def remove_from_queue(uid: int) -> None:
    await run_db(rem_queue_sync, uid)

def create_match_sync(p1: int, p2: int, fee: float) -> Optional[str]:
    try:
        c = get_conn().cursor()
        mid = str(uuid.uuid4())[:8]
        c.execute('INSERT INTO active_matches(match_id, player1_id, player2_id, fee, status, created_at) VALUES(?,?,?,?,?,?)',
                 (mid, p1, p2, fee, 'waiting_for_code', int(time.time())))
        get_conn().commit()
        return mid
    except Exception as e:
        logger.error(f"create_match_sync error: {e}")
        return None

async def create_match(p1: int, p2: int, f: float) -> Optional[str]:
    return await run_db(create_match_sync, p1, p2, f)

def set_room_code_sync(mid: str, code: str) -> None:
    try:
        c = get_conn().cursor()
        c.execute("UPDATE active_matches SET room_code=?, status='in_progress' WHERE match_id=?",
                 (code, mid))
        get_conn().commit()
    except Exception as e:
        logger.error(f"set_room_code_sync error: {e}")

async def set_room_code(m: str, c: str) -> None:
    await run_db(set_room_code_sync, m, c)

def get_match_sync(mid: str) -> Optional[Dict[str, Any]]:
    try:
        c = get_conn().cursor()
        c.execute('SELECT * FROM active_matches WHERE match_id=?', (mid,))
        r = c.fetchone()
        return dict(r) if r else None
    except Exception as e:
        logger.error(f"get_match_sync error: {e}")
        return None

async def get_match(m: str) -> Optional[Dict[str, Any]]:
    return await run_db(get_match_sync, m)

def submit_ss_sync(mid: str, uid: int, fid: str) -> Optional[Dict[str, Any]]:
    try:
        c = get_conn().cursor()
        match = get_match_sync(mid)
        if not match:
            return None
        field = 'p1_screenshot_id' if uid == match['player1_id'] else 'p2_screenshot_id'
        c.execute(f"UPDATE active_matches SET {field}=? WHERE match_id=?", (fid, mid))
        get_conn().commit()
        return get_match_sync(mid)
    except Exception as e:
        logger.error(f"submit_ss_sync error: {e}")
        return None

async def submit_screenshot(m: str, u: int, f: str) -> Optional[Dict[str, Any]]:
    return await run_db(submit_ss_sync, m, u, f)

def calculate_elo(player_rating: int, opponent_rating: int, score: int, k_factor: int = 32) -> int:
    """ELO রেটিং গণনা"""
    expected_score = 1 / (1 + 10**((opponent_rating - player_rating) / 400))
    return int(round(player_rating + k_factor * (score - expected_score)))

def resolve_match_sync(mid: str, wid: int) -> bool:
    try:
        c = get_conn().cursor()
        m = get_match_sync(mid)
        if not m or m['status'] == 'completed':
            return False
        p1, p2, fee = m['player1_id'], m['player2_id'], m['fee']
        lid = p2 if wid == p1 else p1

        u1, u2 = get_user_sync(wid), get_user_sync(lid)
        if not u1 or not u2:
            return False

        nr1 = calculate_elo(u1.get('elo_rating', 1000), u2.get('elo_rating', 1000), 1)
        nr2 = calculate_elo(u2.get('elo_rating', 1000), u1.get('elo_rating', 1000), 0)

        c.execute('UPDATE users SET elo_rating=?, wins=wins+1 WHERE user_id=?', (nr1, wid))
        c.execute('UPDATE users SET elo_rating=?, losses=losses+1 WHERE user_id=?', (nr2, lid))

        if fee > 0:
            adjust_balance_sync(wid, fee * 2 * 0.9, 'match_win')
        c.execute("UPDATE active_matches SET status='completed', winner_id=? WHERE match_id=?",
                 (wid, mid))
        get_conn().commit()
        return True
    except Exception as e:
        logger.error(f"resolve_match_sync error: {e}")
        return False

async def resolve_match(m: str, w: int) -> bool:
    return await run_db(resolve_match_sync, m, w)

def cancel_match_sync(mid: str) -> None:
    try:
        c = get_conn().cursor()
        c.execute("UPDATE active_matches SET status='cancelled' WHERE match_id=?", (mid,))
        get_conn().commit()
    except Exception as e:
        logger.error(f"cancel_match_sync error: {e}")

async def cancel_match(m: str) -> None:
    await run_db(cancel_match_sync, m)

# --- Financial ---
def create_wd_sync(uid: int, amt: float, met: str, num: str) -> Optional[int]:
    try:
        c = get_conn().cursor()
        c.execute('INSERT INTO withdrawal_requests(user_id, amount, method, account_number, created_at) VALUES(?,?,?,?,?)',
                 (uid, amt, met, num, int(time.time())))
        get_conn().commit()
        return c.lastrowid
    except Exception as e:
        logger.error(f"create_wd_sync error: {e}")
        return None

async def create_withdrawal_request(u: int, a: float, m: str, n: str) -> Optional[int]:
    return await run_db(create_wd_sync, u, a, m, n)

def create_dep_sync(uid: int, tx: str, amt: float) -> Optional[int]:
    try:
        c = get_conn().cursor()
        c.execute('INSERT INTO deposit_requests(user_id,txid,amount,created_at) VALUES(?,?,?,?)',
                 (uid, tx, amt, int(time.time())))
        get_conn().commit()
        return c.lastrowid
    except Exception as e:
        logger.error(f"create_dep_sync error: {e}")
        return None

async def create_deposit_request(u: int, t: str, a: float) -> Optional[int]:
    return await run_db(create_dep_sync, u, t, a)

# --- Stats Ops ---
def get_total_users_sync() -> int:
    try:
        c = get_conn().cursor()
        c.execute("SELECT COUNT(*) as c FROM users WHERE is_registered=1")
        return c.fetchone()['c']
    except Exception as e:
        logger.error(f"get_total_users_sync error: {e}")
        return 0

async def get_total_users() -> int:
    return await run_db(get_total_users_sync)

def get_total_matches_sync() -> int:
    try:
        c = get_conn().cursor()
        c.execute("SELECT COUNT(*) as c FROM active_matches WHERE status='completed'")
        return c.fetchone()['c']
    except Exception as e:
        logger.error(f"get_total_matches_sync error: {e}")
        return 0

async def get_total_matches() -> int:
    return await run_db(get_total_matches_sync)

def get_pending_deps_sync() -> int:
    try:
        c = get_conn().cursor()
        c.execute("SELECT COUNT(*) as c FROM deposit_requests WHERE status='pending'")
        return c.fetchone()['c']
    except Exception as e:
        logger.error(f"get_pending_deps_sync error: {e}")
        return 0

async def get_pending_deposits_count() -> int:
    return await run_db(get_pending_deps_sync)

def get_pending_wds_sync() -> int:
    try:
        c = get_conn().cursor()
        c.execute("SELECT COUNT(*) as c FROM withdrawal_requests WHERE status='pending'")
        return c.fetchone()['c']
    except Exception as e:
        logger.error(f"get_pending_wds_sync error: {e}")
        return 0

async def get_pending_withdrawals_count() -> int:
    return await run_db(get_pending_wds_sync)

def get_all_ids_sync() -> List[int]:
    try:
        c = get_conn().cursor()
        c.execute("SELECT user_id FROM users WHERE is_registered=1")
        return [r['user_id'] for r in c.fetchall()]
    except Exception as e:
        logger.error(f"get_all_ids_sync error: {e}")
        return []

async def get_all_user_ids() -> List[int]:
    return await run_db(get_all_ids_sync)

def get_top_wins_sync(limit: int = 10) -> List[Dict[str, Any]]:
    try:
        c = get_conn().cursor()
        c.execute('SELECT ingame_name, wins, elo_rating FROM users WHERE is_registered=1 ORDER BY elo_rating DESC LIMIT ?',
                 (limit,))
        return [dict(r) for r in c.fetchall()]
    except Exception as e:
        logger.error(f"get_top_wins_sync error: {e}")
        return []

async def get_top_wins(l: int = 10) -> List[Dict[str, Any]]:
    return await run_db(get_top_wins_sync, l)

# --- Lock for thread safety ---
_lock = asyncio.Lock()
