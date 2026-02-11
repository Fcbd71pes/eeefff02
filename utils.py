# utils.py - Utility Functions for Better Code Quality
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
from functools import wraps

logger = logging.getLogger(__name__)

# --- Rate Limiting ---
class RateLimiter:
    """প্রতি ইউজার রেট লিমিটিং"""
    def __init__(self, max_requests: int = 5, window_seconds: int = 10):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[int, list] = {}

    def is_allowed(self, user_id: int) -> bool:
        """ইউজারকে অনুমতি দিতে পারা যায় কিনা চেক করুন"""
        now = time.time()
        if user_id not in self.requests:
            self.requests[user_id] = []

        # পুরনো requests সরান
        self.requests[user_id] = [t for t in self.requests[user_id]
                                  if now - t < self.window_seconds]

        if len(self.requests[user_id]) < self.max_requests:
            self.requests[user_id].append(now)
            return True
        return False

    def get_remaining(self, user_id: int) -> int:
        """বাকি কতটা রিকোয়েস্ট করা যাবে"""
        now = time.time()
        if user_id not in self.requests:
            return self.max_requests

        self.requests[user_id] = [t for t in self.requests[user_id]
                                  if now - t < self.window_seconds]
        return max(0, self.max_requests - len(self.requests[user_id]))

# গ্লোবাল রেট লিমিটার
rate_limiter = RateLimiter(max_requests=10, window_seconds=30)

# --- Input Validation ---
def validate_phone_number(phone: str) -> Tuple[bool, str]:
    """বাংলাদেশের ফোন নম্বর ভ্যালিডেট করুন"""
    if not phone:
        return False, "ফোন নম্বর খালি।"

    # শুধু সংখ্যা এবং হাইফেন থাকতে পারে
    clean_phone = phone.replace('-', '').replace(' ', '')

    # ১১-১৯ সংখ্যার মধ্যে থাকতে পারে বাংলাদেশে
    if not (clean_phone.isdigit() and 10 <= len(clean_phone) <= 13):
        return False, "সঠিক ফোন নম্বর দিন। (11-13 অঙ্ক)"

    return True, clean_phone

def validate_amount(amount_str: str, min_amount: float = 0) -> Tuple[bool, float, str]:
    """টাকার পরিমাণ ভ্যালিডেট করুন"""
    try:
        amount = float(amount_str)
        if amount < min_amount:
            return False, 0, f"ন্যূনতম পরিমাণ: {min_amount} TK"
        if amount > 1000000:  # ১০ লক্ষ সীমা
            return False, 0, "অনেক বেশি টাকা। সর্বোচ্চ ১000000 TK"
        if amount != amount:  # NaN চেক
            return False, 0, "সঠিক সংখ্যা দিন।"
        return True, amount, ""
    except (ValueError, TypeError):
        return False, 0, "সংখ্যা দিন।"

def validate_username(username: str) -> Tuple[bool, str]:
    """গেম নিকনেম ভ্যালিডেট করুন"""
    if not username or len(username) < 2:
        return False, "নাম অন্তত ২ অক্ষর হতে হবে।"

    if len(username) > 50:
        return False, "নাম ৫০ অক্ষরের কম হতে হবে।"

    # শুধু আলফানিউমেরিক, স্পেস, এবং আন্ডারস্কোর
    if not re.match(r'^[\w\s\-]{2,50}$', username):
        return False, "শুধুমাত্র অক্ষর, সংখ্যা, স্পেস এবং হাইফেন ব্যবহার করুন।"

    return True, username.strip()

# --- Text Processing ---
def truncate_text(text: str, max_length: int = 500) -> str:
    """টেক্সট ছোট করুন"""
    if len(text) > max_length:
        return text[:max_length-3] + '...'
    return text

def clean_text(text: str) -> str:
    """এক্সট্রা স্পেস এবং নিউলাইন সরান"""
    return ' '.join(text.split())

def format_balance(balance: float) -> str:
    """ব্যালেন্স ফর্ম্যাট করুন"""
    return f"{balance:,.2f}"

def format_datetime(dt: datetime) -> str:
    """ডেটটাইম ফর্ম্যাট করুন (বাংলায়)"""
    months = ['জানু', 'ফেব', 'মার্চ', 'এপ্রিল', 'মে', 'জুন',
              'জুলাই', 'আগ', 'সেপ', 'অক্টো', 'নভেম', 'ডিসেম']

    day = dt.day
    month = months[dt.month - 1]
    year = dt.year
    hour = dt.hour
    minute = dt.minute

    return f"{day} {month} {year}, {hour:02d}:{minute:02d}"

# --- Decorators ---
def safe_async_handler(func):
    """Async হ্যান্ডলার সুরক্ষিত করুন"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
            # আপডেট এবং context আছে কিনা চেক করুন
            if args and hasattr(args[0], 'message'):
                try:
                    await args[0].message.reply_text("একটি ত্রুটি ঘটেছে। আবার চেষ্টা করুন।")
                except:
                    pass
    return wrapper

def log_user_action(action_name: str):
    """ইউজার অ্যাকশন লগ করুন"""
    def decorator(func):
        @wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            user_id = update.effective_user.id if update.effective_user else "Unknown"
            logger.info(f"Action '{action_name}' by user {user_id}")
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator

# --- File/Path Helpers (Termux Compatible) ---
def ensure_directory(path):
    """ডিরেক্টরি নিশ্চিত করুন"""
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create directory {path}: {e}")
        return False

# --- Time Helpers ---
def get_time_until_reset() -> int:
    """মধ্যরাত পর্যন্ত সেকেন্ড পান"""
    now = datetime.now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((tomorrow - now).total_seconds())

def is_within_hours(target_time: datetime, hours: int) -> bool:
    """সময় নির্দিষ্ট ঘণ্টার মধ্যে আছে কিনা চেক করুন"""
    elapsed = (datetime.now() - target_time).total_seconds()
    return elapsed < (hours * 3600)

# --- ELO Calculation Helper ---
def calculate_elo_gain(player_elo: int, opponent_elo: int, won: bool, k_factor: int = 32) -> int:
    """ELO পয়েন্ট লাভ গণনা করুন"""
    expected = 1 / (1 + 10**((opponent_elo - player_elo) / 400))
    outcome = 1 if won else 0
    return int(round(k_factor * (outcome - expected)))
