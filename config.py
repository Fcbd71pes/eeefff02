# config.py - Termux Compatible
import os
from pathlib import Path

# --- Bot Settings ---
TOKEN = os.getenv('BOT_TOKEN', '8010407192:AAH-9yMHbBsxcUE4Ss4WEkCVMX_U_a901C8')
ADMINS = [5172723202]

# --- Channels ---
CHANNEL_ID = -1003079996041
LOBBY_CHANNEL_ID = -1003079996041
CHANNEL_USERNAME = 'xefootball_esports'
BOT_USERNAME = 'esfootball_tournament_bot'

# --- Financial ---
MINIMUM_DEPOSIT = 50.0
MINIMUM_WITHDRAWAL = 100.0
REFERRAL_BONUS = 5.0
BKASH_NUMBER = '01914573762'
NAGAD_NUMBER = '01914573762'

# --- AI Settings (GROQ API) ---
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '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')

# --- Database Settings ---
# Termux সামঞ্জস্যপূর্ণ পথ
BASE_DIR = Path.home() / '.eFootball_bot'
BASE_DIR.mkdir(exist_ok=True)
LOCAL_DB = str(BASE_DIR / 'local_data.db')
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = str(LOGS_DIR / 'bot.log')

# --- System Settings ---
MAX_WORKERS = 4
DB_TIMEOUT = 30
REQUEST_TIMEOUT = 30
