# db.py - Fixed Version
import sqlite3
import time
import asyncio
import logging
from datetime import datetime
import uuid
import config

logger = logging.getLogger(__name__)
_conn = None

def get_conn():
    global _conn
    if _conn is None: 
        _conn = sqlite3.connect(config.LOCAL_DB, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn

def init_db():
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
    
    # নতুন কলাম যোগ করার জন্য নিরাপদ কোড (SyntaxError ফিক্স)
    try:
        c.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
    except Exception:
        pass
    
    try:
        c.execute("ALTER TABLE users ADD COLUMN elo_rating INTEGER DEFAULT 1000")
    except Exception:
        pass
        
    conn.commit()

# --- Async Helper ---
async def run_db(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args))

# --- Settings ---
def get_setting_sync(key):
    c = get_conn().cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    r = c.fetchone()
    return r['value'] if r else None
async def get_setting(key): return await run_db(get_setting_sync, key)

def set_setting_sync(key, value):
    c = get_conn().cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    get_conn().commit()
async def set_setting(key, v): await run_db(set_setting_sync, key, v)

# --- User Functions ---
def get_user_sync(uid): 
    c=get_conn().cursor()
    c.execute('SELECT * FROM users WHERE user_id=?',(uid,))
    r=c.fetchone()
    return dict(r) if r else None
async def get_user(uid): return await run_db(get_user_sync, uid)

def create_user_sync(uid, name, ref): 
    c=get_conn().cursor()
    c.execute('INSERT OR IGNORE INTO users(user_id, ingame_name, created_at) VALUES(?,?,?)', (uid, name, datetime.now()))
    if ref: c.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (ref, uid))
    get_conn().commit()
async def create_user_if_not_exists(u,n,r): await run_db(create_user_sync, u,n,r)

def update_user_fields_sync(uid, data): 
    c=get_conn().cursor()
    sets=','.join([f"{k}=?" for k in data.keys()])
    params=list(data.values())+[uid]
    c.execute(f'UPDATE users SET {sets} WHERE user_id=?', params)
    get_conn().commit()
async def update_user_fields(uid, data): await run_db(update_user_fields_sync, uid, data)

async def set_user_state(uid, s, d=None): await update_user_fields(uid, {'state': s, 'state_data': d})

def adjust_balance_sync(uid, amt, type, note=''): 
    c=get_conn().cursor()
    c.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(amt,uid))
    c.execute('INSERT INTO transactions(user_id, amount, type, note, created_at) VALUES(?,?,?,?,?)',(uid, amt, type, note, int(time.time())))
    get_conn().commit()
async def adjust_balance(uid, amt, type, note=''): await run_db(adjust_balance_sync, uid, amt, type, note)

# --- Matchmaking ---
def find_opp_sync(fee, exc_uid):
    c = get_conn().cursor()
    c.execute('SELECT * FROM matchmaking_queue WHERE fee = ? AND user_id != ? LIMIT 1', (fee, exc_uid))
    r = c.fetchone()
    return dict(r) if r else None
async def find_opponent_in_queue(f, e): return await run_db(find_opp_sync, f, e)

def add_queue_sync(uid, fee, mid): 
    c=get_conn().cursor()
    c.execute('INSERT OR REPLACE INTO matchmaking_queue(user_id,fee,joined_at,lobby_message_id) VALUES(?,?,?,?)',(uid,fee,int(time.time()),mid))
    get_conn().commit()
async def add_to_queue(u,f,m): await run_db(add_queue_sync, u,f,m)

def rem_queue_sync(uid): 
    c=get_conn().cursor()
    c.execute('DELETE FROM matchmaking_queue WHERE user_id=?',(uid,))
    get_conn().commit()
async def remove_from_queue(uid): await run_db(rem_queue_sync, uid)

def create_match_sync(p1, p2, fee): 
    c=get_conn().cursor()
    mid=str(uuid.uuid4())[:8]
    c.execute('INSERT INTO active_matches(match_id, player1_id, player2_id, fee, status, created_at) VALUES(?,?,?,?,?,?)',(mid, p1, p2, fee, 'waiting_for_code', int(time.time())))
    get_conn().commit()
    return mid
async def create_match(p1,p2,f): return await run_db(create_match_sync, p1,p2,f)

def set_room_code_sync(mid, code): 
    c=get_conn().cursor()
    c.execute("UPDATE active_matches SET room_code=?, status='in_progress' WHERE match_id=?", (code, mid))
    get_conn().commit()
async def set_room_code(m,c): await run_db(set_room_code_sync, m,c)

def get_match_sync(mid): 
    c=get_conn().cursor()
    c.execute('SELECT * FROM active_matches WHERE match_id=?',(mid,))
    r=c.fetchone()
    return dict(r) if r else None
async def get_match(m): return await run_db(get_match_sync, m)

def submit_ss_sync(mid, uid, fid):
    c=get_conn().cursor()
    match = get_match_sync(mid)
    if not match: return None
    field = 'p1_screenshot_id' if uid == match['player1_id'] else 'p2_screenshot_id'
    c.execute(f"UPDATE active_matches SET {field}=? WHERE match_id=?", (fid, mid))
    get_conn().commit()
    return get_match_sync(mid)
async def submit_screenshot(m,u,f): return await run_db(submit_ss_sync, m,u,f)

def calculate_elo(player_rating, opponent_rating, score, k_factor=32):
    expected_score = 1 / (1 + 10**((opponent_rating - player_rating) / 400))
    return int(round(player_rating + k_factor * (score - expected_score)))

def resolve_match_sync(mid, wid):
    c=get_conn().cursor()
    m=get_match_sync(mid)
    if not m or m['status'] == 'completed': return False
    p1, p2, fee = m['player1_id'], m['player2_id'], m['fee']
    lid = p2 if wid == p1 else p1
    
    u1, u2 = get_user_sync(wid), get_user_sync(lid)
    nr1 = calculate_elo(u1.get('elo_rating',1000), u2.get('elo_rating',1000), 1)
    nr2 = calculate_elo(u2.get('elo_rating',1000), u1.get('elo_rating',1000), 0)
    
    c.execute('UPDATE users SET elo_rating=?, wins=wins+1 WHERE user_id=?',(nr1, wid))
    c.execute('UPDATE users SET elo_rating=?, losses=losses+1 WHERE user_id=?',(nr2, lid))
    
    if fee > 0: adjust_balance_sync(wid, fee*2*0.9, 'match_win')
    c.execute("UPDATE active_matches SET status='completed', winner_id=? WHERE match_id=?",(wid, mid))
    get_conn().commit()
    return True
async def resolve_match(m,w): return await run_db(resolve_match_sync, m,w)

def cancel_match_sync(mid): 
    c=get_conn().cursor()
    c.execute("UPDATE active_matches SET status='cancelled' WHERE match_id=?",(mid,))
    get_conn().commit()
async def cancel_match(m): await run_db(cancel_match_sync, m)

# --- Financial ---
def create_wd_sync(uid, amt, met, num): 
    c=get_conn().cursor()
    c.execute('INSERT INTO withdrawal_requests(user_id, amount, method, account_number, created_at) VALUES(?,?,?,?,?)', (uid, amt, met, num, int(time.time())))
    get_conn().commit()
    return c.lastrowid
async def create_withdrawal_request(u,a,m,n): return await run_db(create_wd_sync, u,a,m,n)

def create_dep_sync(uid, tx, amt): 
    c=get_conn().cursor()
    c.execute('INSERT INTO deposit_requests(user_id,txid,amount,created_at) VALUES(?,?,?,?)',(uid,tx,amt,int(time.time())))
    get_conn().commit()
    return c.lastrowid
async def create_deposit_request(u,t,a): return await run_db(create_dep_sync, u,t,a)

# --- Stats Ops ---
def get_total_users_sync(): 
    c=get_conn().cursor()
    c.execute("SELECT COUNT(*) as c FROM users WHERE is_registered=1")
    return c.fetchone()['c']
async def get_total_users(): return await run_db(get_total_users_sync)

def get_total_matches_sync():
    c=get_conn().cursor()
    c.execute("SELECT COUNT(*) as c FROM active_matches WHERE status='completed'")
    return c.fetchone()['c']
async def get_total_matches(): return await run_db(get_total_matches_sync)

def get_pending_deps_sync(): 
    c=get_conn().cursor()
    c.execute("SELECT COUNT(*) as c FROM deposit_requests WHERE status='pending'")
    return c.fetchone()['c']
async def get_pending_deposits_count(): return await run_db(get_pending_deps_sync)

def get_pending_wds_sync(): 
    c=get_conn().cursor()
    c.execute("SELECT COUNT(*) as c FROM withdrawal_requests WHERE status='pending'")
    return c.fetchone()['c']
async def get_pending_withdrawals_count(): return await run_db(get_pending_wds_sync)

def get_all_ids_sync(): 
    c=get_conn().cursor()
    c.execute("SELECT user_id FROM users WHERE is_registered=1")
    return [r['user_id'] for r in c.fetchall()]
async def get_all_user_ids(): return await run_db(get_all_ids_sync)

def get_top_wins_sync(limit=10): 
    c=get_conn().cursor()
    c.execute('SELECT ingame_name, wins, elo_rating FROM users WHERE is_registered=1 ORDER BY elo_rating DESC LIMIT ?',(limit,))
    return [dict(r) for r in c.fetchall()]
async def get_top_wins(l=10): return await run_db(get_top_wins_sync, l)

# --- Lock ---
_lock = asyncio.Lock()
