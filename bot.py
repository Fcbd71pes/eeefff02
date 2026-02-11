# bot.py - Termux Compatible & Enhanced
import logging
import re
import json
import asyncio
import signal
import sys
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import db
import config
import ai_manager

# --- Logging Setup ---
import os
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),  # লগ ফাইলে সেভ করা
        logging.StreamHandler()  # কনসোলেও প্রদর্শন
    ]
)
logger = logging.getLogger(__name__)

# --- Keyboards ---
MAIN_KEYBOARD = ReplyKeyboardMarkup([
    ["🎮 Play 1v1", "💰 My Wallet"],
    ["📋 Profile", "📜 Rules"],
    ["🏆 Leaderboard", "🤖 AI Support"]
], resize_keyboard=True)
CANCEL_KEYBOARD = ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)

# --- Global Application Reference ---
app_instance = None

async def ensure_user(update: Update, referrer_id: int = None):
    """ইউজার তৈরি বা পান"""
    user_obj = update.effective_user
    if not user_obj:
        return None
    if not await db.get_user(user_obj.id):
        await db.create_user_if_not_exists(user_obj.id, user_obj.username or user_obj.first_name, referrer_id)
    user = await db.get_user(user_obj.id)
    if user and user.get('is_banned'):
        return None
    return user

async def check_channel_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """চ্যানেল মেম্বার চেক"""
    user_id = update.effective_user.id
    if user_id in config.ADMINS:
        return True
    try:
        member = await context.bot.get_chat_member(config.CHANNEL_ID, user_id)
        if member.status in ('left', 'kicked'):
            kb = [[InlineKeyboardButton('Join Channel', url=f'https://t.me/{config.CHANNEL_USERNAME}')]]
            await update.effective_message.reply_text('বটটি ব্যবহার করতে, অনুগ্রহ করে আমাদের চ্যানেলে যোগ দিন।', reply_markup=InlineKeyboardMarkup(kb))
            return False
        return True
    except Exception as e:
        logger.warning(f"Channel check failed for user {user_id}: {e}")
        return False

# --- Commands ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """স্টার্ট কমান্ড"""
    try:
        user = update.effective_user
        args = context.args
        referrer_id = int(args[0].split('_')[1]) if args and args[0].startswith('ref_') else None
        db_user = await ensure_user(update, referrer_id)

        if db_user and db_user.get('is_banned'):
            return await update.message.reply_text("❌ আপনার একাউন্ট ব্যান করা হয়েছে।")

        if not db_user:
            return

        if not await check_channel_member(update, context):
            return

        if db_user.get('is_registered'):
            await update.message.reply_text(f'স্বাগতম! আমি আপনার AI অ্যাডমিন।', reply_markup=MAIN_KEYBOARD)
        else:
            await update.message.reply_text('স্বাগতম! আপনার eFootball ইন-গেম নাম (IGN) দিন:', reply_markup=CANCEL_KEYBOARD)
            await db.set_user_state(db_user['user_id'], 'awaiting_ign')
    except Exception as e:
        logger.error(f"Error in start_command: {e}")
        await update.message.reply_text("একটি ত্রুটি ঘটেছে। পরে চেষ্টা করুন।")

async def main_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """টেক্সট মেসেজ হ্যান্ডলার"""
    try:
        user = await ensure_user(update)
        if not user or user.get('is_banned'):
            return
        txt = update.message.text.strip()
        state, state_data = user.get('state'), user.get('state_data')

        if txt == "📜 Rules":
            return await rules_command(update, context)
        if txt == "🤖 AI Support":
            return await update.message.reply_text("আপনার প্রশ্নটি লিখুন। যেমন: '/ask কিভাবে খেলবো?'")
        if txt == "❌ Cancel":
            await db.set_user_state(user['user_id'], None)
            await db.remove_from_queue(user['user_id'])
            return await update.message.reply_text("বাতিল করা হয়েছে।", reply_markup=MAIN_KEYBOARD)

        # State Machine
        if state == 'awaiting_ign':
            await db.update_user_fields(user['user_id'], {'ingame_name': txt})
            await db.set_user_state(user['user_id'], 'awaiting_phone')
            return await update.message.reply_text('ধন্যবাদ! ফোন নম্বর দিন:')

        if state == 'awaiting_phone':
            await db.update_user_fields(user['user_id'], {'phone_number': txt, 'is_registered': 1})
            if not user.get('welcome_given'):
                await db.adjust_balance(user['user_id'], 10.0, 'welcome_bonus')
                await db.update_user_fields(user['user_id'], {'welcome_given': 1})
            await db.set_user_state(user['user_id'], None)
            return await update.message.reply_text('রেজিস্ট্রেশন সম্পন্ন!', reply_markup=MAIN_KEYBOARD)

        if state == 'awaiting_room_code':
            match_id = state_data
            await db.set_room_code(match_id, txt)
            match = await db.get_match(match_id)
            if match:
                await context.bot.send_message(user['user_id'], f"রুম কোড `{txt}` পাঠানো হয়েছে।", parse_mode='Markdown', reply_markup=MAIN_KEYBOARD)
                await context.bot.send_message(match['player2_id'], f"⚔️ ম্যাচ শুরু!\nRoom Code: `{txt}`\nখেলা শেষে স্ক্রিনশট দিন।", parse_mode='Markdown')
                context.job_queue.run_once(check_match_timeout, timedelta(minutes=15), data={'match_id': match_id})
            return await db.set_user_state(user['user_id'], None)

        if state == 'awaiting_withdraw_amount':
            try:
                amt = float(txt)
                if amt < config.MINIMUM_WITHDRAWAL:
                    return await update.message.reply_text(f"ন্যূনতম উত্তোলন: {config.MINIMUM_WITHDRAWAL} TK")
                kb = [[InlineKeyboardButton('Bkash', callback_data='w_method_bkash')], [InlineKeyboardButton('Nagad', callback_data='w_method_nagad')]]
                await db.set_user_state(user['user_id'], 'awaiting_withdraw_method', json.dumps({'amount': amt}))
                return await update.message.reply_text("মাধ্যম নির্বাচন করুন:", reply_markup=InlineKeyboardMarkup(kb))
            except ValueError:
                return await update.message.reply_text("সঠিক সংখ্যা দিন।")

        if state == 'awaiting_withdraw_account':
            data = json.loads(state_data)
            await db.adjust_balance(user['user_id'], -data['amount'], 'withdrawal_request')
            req_id = await db.create_withdrawal_request(user['user_id'], data['amount'], data['method'], txt)
            await update.message.reply_text("রিকোয়েস্ট সফল।", reply_markup=MAIN_KEYBOARD)
            for a in config.ADMINS:
                try:
                    await context.bot.send_message(a, f"New Withdraw: {req_id} | {data['amount']}TK | {txt}")
                except Exception as e:
                    logger.warning(f"Failed to notify admin {a}: {e}")
            return await db.set_user_state(user['user_id'], None)

        # Menu
        if txt == "🎮 Play 1v1":
            return await play_menu(update, context)
        if txt == "💰 My Wallet":
            return await wallet_menu(update, context)
        if txt == "📋 Profile":
            return await show_profile(update, context)
        if txt == "🏆 Leaderboard":
            return await show_leaderboard(update, context)

        # Deposit Regex
        m = re.match(r'^([A-Za-z0-9]+)\s+(\d+(?:\.\d{1,2})?)$', txt)
        if m:
            await db.create_deposit_request(user['user_id'], m.group(1), float(m.group(2)))
            await update.message.reply_text("ডিপোজিট রিকোয়েস্ট জমা হয়েছে।")
            for a in config.ADMINS:
                try:
                    await context.bot.send_message(a, f"New Deposit: {m.group(2)}TK")
                except Exception as e:
                    logger.warning(f"Failed to notify admin {a}: {e}")
            return

        # AI Fallback
        if not state:
            await context.bot.send_chat_action(chat_id=user['user_id'], action="typing")
            ai_reply = await ai_manager.get_ai_response(txt, user)
            await update.message.reply_text(f"🤖 {ai_reply}")
    except Exception as e:
        logger.error(f"Error in main_text_handler: {e}")
        await update.message.reply_text("একটি ত্রুটি ঘটেছে। পরে চেষ্টা করুন।")

async def ask_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI রিকোয়েস্ট কমান্ড"""
    try:
        if not context.args:
            return await update.message.reply_text("ব্যবহার: /ask <আপনার প্রশ্ন>")
        user = await ensure_user(update)
        res = await ai_manager.get_ai_response(" ".join(context.args), user)
        await update.message.reply_text(f"🤖 {res}")
    except Exception as e:
        logger.error(f"Error in ask_ai: {e}")
        await update.message.reply_text("AI রেসপন্স পেতে ব্যর্থ।")

# --- Helper Views ---
async def play_menu(update, context):
    """খেলার মেনু"""
    kb = [[InlineKeyboardButton(f'{f} TK', callback_data=f'play_fee_{f}') for f in [20, 50, 100]]]
    if await db.get_setting('free_play_status') == 'on':
        kb.insert(0, [InlineKeyboardButton('Free Match', callback_data='play_fee_0')])
    await update.message.reply_text('এন্ট্রি ফি নির্বাচন করুন:', reply_markup=InlineKeyboardMarkup(kb))

async def wallet_menu(update, context):
    """ওয়ালেট মেনু"""
    u = await ensure_user(update)
    kb = [[InlineKeyboardButton('➕ Deposit', callback_data='deposit'), InlineKeyboardButton('➖ Withdraw', callback_data='withdraw')]]
    await update.message.reply_text(f"ব্যালেন্স: {u.get('balance',0):.2f} TK", reply_markup=InlineKeyboardMarkup(kb))

async def show_profile(update, context):
    """প্রোফাইল দেখান"""
    u = await ensure_user(update)
    await update.message.reply_text(f"👤 নাম: {u['ingame_name']}\n🏆 জিতেছে: {u['wins']}\n🎖 ELO: {u['elo_rating']}")

async def show_leaderboard(update, context):
    """লিডারবোর্ড দেখান"""
    rows = await db.get_top_wins(5)
    txt = "\n".join([f"{i+1}. {r['ingame_name']} ({r['elo_rating']})" for i, r in enumerate(rows)])
    await update.message.reply_text(f"🏆 সেরা খেলোয়াড়:\n{txt}")

# --- Match Logic ---
async def handle_play_callback(update, context):
    """খেলা কল ব্যাক হ্যান্ডলার"""
    try:
        q = update.callback_query
        fee = float(q.data.split('_')[-1])
        uid = q.from_user.id
        u = await db.get_user(uid)

        if fee > 0 and u['balance'] < fee:
            return await q.message.reply_text("❌ অপর্যাপ্ত ব্যালেন্স।")

        async with db._lock:
            opp = await db.find_opponent_in_queue(fee, uid)
            if opp:
                # Match Found
                p2 = await db.get_user(opp['user_id'])
                if p2:
                    await db.remove_from_queue(p2['user_id'])
                    mid = await db.create_match(uid, p2['user_id'], fee)
                    try:
                        await context.bot.delete_message(config.LOBBY_CHANNEL_ID, opp['lobby_message_id'])
                    except:
                        pass

                    await context.bot.send_message(uid, f"✅ প্রতিপক্ষ: {p2['ingame_name']}! রুম কোড দিন।", reply_markup=CANCEL_KEYBOARD)
                    await db.set_user_state(uid, 'awaiting_room_code', mid)
                    await context.bot.send_message(p2['user_id'], "✅ প্রতিপক্ষ পাওয়া গেছে! রুম কোডের জন্য অপেক্ষা করুন।")
                    await q.message.edit_text("ম্যাচ শুরু হচ্ছে...")
            else:
                # Add to Queue
                txt = f"🔥 **New Match!**\nPlayer: {u['ingame_name']}\nFee: {fee} TK"
                msg = await context.bot.send_message(config.LOBBY_CHANNEL_ID, txt, parse_mode='Markdown')
                await db.add_to_queue(uid, fee, msg.message_id)
                await q.message.edit_text("🔍 প্রতিপক্ষ খোঁজা হচ্ছে...", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{uid}")]]))
    except Exception as e:
        logger.error(f"Error in handle_play_callback: {e}")

async def check_match_timeout(context):
    """ম্যাচ টাইমআউট চেক"""
    try:
        mid = context.job.data['match_id']
        await db.cancel_match(mid)
    except Exception as e:
        logger.error(f"Error in check_match_timeout: {e}")

async def photo_handler(update, context):
    """ফটো হ্যান্ডলার"""
    try:
        user = await ensure_user(update)
        if user.get('state') == 'awaiting_screenshot':
            mid = user['state_data']
            fid = update.message.photo[-1].file_id
            match = await db.submit_screenshot(mid, user['user_id'], fid)
            await update.message.reply_text("✅ স্ক্রিনশট জমা হয়েছে।", reply_markup=MAIN_KEYBOARD)
            await db.set_user_state(user['user_id'], None)

            # Notify Admin
            if match and match['p1_screenshot_id'] and match['p2_screenshot_id']:
                for a in config.ADMINS:
                    try:
                        kb = [[InlineKeyboardButton("P1 Win", callback_data=f"admin_res_{mid}_{match['player1_id']}"),
                               InlineKeyboardButton("P2 Win", callback_data=f"admin_res_{mid}_{match['player2_id']}")]]
                        await context.bot.send_message(a, f"Match #{mid} Review:", reply_markup=InlineKeyboardMarkup(kb))
                        await context.bot.send_photo(a, match['p1_screenshot_id'], caption="Player 1")
                        await context.bot.send_photo(a, match['p2_screenshot_id'], caption="Player 2")
                    except Exception as e:
                        logger.warning(f"Failed to notify admin {a}: {e}")
    except Exception as e:
        logger.error(f"Error in photo_handler: {e}")

async def cb_handler(update, context):
    """কল ব্যাক হ্যান্ডলার"""
    try:
        q = update.callback_query
        await q.answer()
        d = q.data

        if d.startswith('play_fee_'):
            await handle_play_callback(update, context)
        elif d == 'deposit':
            await q.message.reply_text(f"Send Money to `{config.BKASH_NUMBER}` and give TrxID.", parse_mode='Markdown')
        elif d == 'withdraw':
            await db.set_user_state(q.from_user.id, 'awaiting_withdraw_amount')
            await q.message.reply_text("টাকার পরিমাণ লিখুন:", reply_markup=CANCEL_KEYBOARD)
        elif d.startswith('w_method_'):
            u = await db.get_user(q.from_user.id)
            if u and u['state_data']:
                dat = json.loads(u['state_data'])
                dat['method'] = d.split('_')[2]
                await db.set_user_state(q.from_user.id, 'awaiting_withdraw_account', json.dumps(dat))
                await q.message.edit_text("আপনার নম্বরটি দিন:")
        elif d.startswith('cancel_'):
            await db.remove_from_queue(int(d.split('_')[1]))
            await q.message.edit_text("বাতিল করা হয়েছে।")
        elif d.startswith('admin_res_'):
            if q.from_user.id in config.ADMINS:
                parts = d.split('_')
                if await db.resolve_match(parts[2], int(parts[3])):
                    await q.message.edit_caption(caption="✅ Match Resolved.")
                    await context.bot.send_message(int(parts[3]), "অভিনন্দন! আপনি জিতেছেন।")
    except Exception as e:
        logger.error(f"Error in cb_handler: {e}")

# --- Admin Commands ---
async def stats_cmd(update, context):
    """স্ট্যাটিস্টিক্স কমান্ড"""
    try:
        if update.effective_user.id in config.ADMINS:
            u = await db.get_total_users()
            m = await db.get_total_matches()
            await update.message.reply_text(f"Users: {u}\nMatches: {m}")
    except Exception as e:
        logger.error(f"Error in stats_cmd: {e}")

async def broadcast_cmd(update, context):
    """ব্রডকাস্ট কমান্ড"""
    try:
        if update.effective_user.id in config.ADMINS:
            users = await db.get_all_user_ids()
            msg = " ".join(context.args)
            sent = 0
            for u in users:
                try:
                    await context.bot.send_message(u, msg)
                    sent += 1
                except:
                    pass
            await update.message.reply_text(f"Broadcast sent to {sent} users.")
    except Exception as e:
        logger.error(f"Error in broadcast_cmd: {e}")

async def rules_command(update, context):
    """রুলস কমান্ড"""
    try:
        r = await db.get_setting('rules_text')
        await update.message.reply_text(r or "No rules set.")
    except Exception as e:
        logger.error(f"Error in rules_command: {e}")

async def set_rules(update, context):
    """রুলস সেট কমান্ড"""
    try:
        if update.effective_user.id in config.ADMINS:
            await db.set_setting('rules_text', " ".join(context.args))
            await update.message.reply_text("Rules updated.")
    except Exception as e:
        logger.error(f"Error in set_rules: {e}")

# --- Signal Handlers for Graceful Shutdown ---
async def signal_handler(signum, frame):
    """গ্রেসফুল শাটডাউন হ্যান্ডলার (Termux Compatible)"""
    try:
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        if app_instance:
            await app_instance.stop()
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    finally:
        sys.exit(0)

def main():
    """মেইন ফাংশন"""
    global app_instance
    try:
        db.init_db()
        app = Application.builder().token(config.TOKEN).build()
        app_instance = app

        # Handlers
        app.add_handler(CommandHandler('start', start_command))
        app.add_handler(CommandHandler('ask', ask_ai))
        app.add_handler(CommandHandler('rules', rules_command))
        app.add_handler(CommandHandler('stats', stats_cmd))
        app.add_handler(CommandHandler('broadcast', broadcast_cmd))
        app.add_handler(CommandHandler('setrules', set_rules))

        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_text_handler))
        app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
        app.add_handler(CallbackQueryHandler(cb_handler))

        # Signal handling for graceful shutdown
        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        except (OSError, RuntimeError) as e:
            logger.warning(f"Signal handling not available on this platform: {e}")

        logger.info("🚀 Bot Starting (Termux Compatible)...")
        app.run_polling()
    except Exception as e:
        logger.critical(f"Critical error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
