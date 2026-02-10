# ai_manager.py - Free Magic API Version
import requests
import config
import logging
import db
import asyncio

logger = logging.getLogger(__name__)

async def get_ai_response(user_query, user_info=None):
    # 1. ডাটাবেস থেকে রুলস আনা
    try:
        rules = await db.get_setting('rules_text')
        if not rules: rules = "সাধারণ eFootball নিয়মাবলী প্রযোজ্য।"
    except:
        rules = "সাধারণ নিয়মাবলী।"

    # 2. ইউজার ইনফো
    user_name = user_info.get('ingame_name', 'Guest') if user_info else 'Guest'
    user_balance = user_info.get('balance', 0) if user_info else 0

    # 3. প্রম্পট তৈরি (System Prompt)
    system_prompt = f'''
    You are the AI Admin of 'eFootball Tournament Bot'.
    Language: Bengali (Bangla).
    Keep replies short, friendly, and helpful.
    
    Bot Info:
    - Name: {config.BOT_USERNAME}
    - Bkash/Nagad: {config.BKASH_NUMBER}
    - Min Deposit: {config.MINIMUM_DEPOSIT} TK
    
    Rules: {rules}
    
    User: {user_name} (Bal: {user_balance} TK)
    
    Instruction: Answer the user question in Bangla. If they ask about money issues, tell them to contact the human admin.
    '''

    # 4. Free Magic API (Pollinations AI)
    # কোন API Key লাগে না, সরাসরি কাজ করে
    url = "https://text.pollinations.ai/"
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    data = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ],
        "model": "openai", # এটি ফ্রীতে ভালো মডেল ব্যবহার করে
        "seed": 42
    }

    try:
        # 5. রিকোয়েস্ট পাঠানো
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: requests.post(url, headers=headers, json=data))
        
        if response.status_code == 200:
            # Pollinations সরাসরি টেক্সট রিটার্ন করে
            return response.text
        else:
            logger.error(f"API Error: {response.status_code} - {response.text}")
            return "সার্ভারে একটু সমস্যা হচ্ছে।"

    except Exception as e:
        logger.error(f"Network Error: {e}")
        return "ইন্টারনেট সংযোগে সমস্যা।"