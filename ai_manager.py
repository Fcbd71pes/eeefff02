# ai_manager.py - Groq API Version (Enhanced)
import requests
import config
import logging
import db
import asyncio
import json
from typing import Optional, Dict, Any
import time

logger = logging.getLogger(__name__)

# Retry mechanism
MAX_RETRIES = 2
RETRY_DELAY = 1  # второе

async def get_ai_response(user_query: str, user_info: Optional[Dict[str, Any]] = None, retry_count: int = 0) -> str:
    """
    Groq API ব্যবহার করে AI রেসপন্সপান (উন্নত সংস্করণ)
    """
    try:
        # 1. ডাটাবেস থেকে রুলস আনা
        try:
            rules = await db.get_setting('rules_text')
            if not rules:
                rules = "সাধারণ eFootball নিয়মাবলী প্রযোজ্য।"
        except Exception as e:
            logger.warning(f"Failed to fetch rules: {e}")
            rules = "সাধারণ নিয়মাবলী।"

        # 2. ইউজার ইনফো নিরাপদে পান
        user_name = 'Guest'
        user_balance = 0
        user_wins = 0

        if user_info:
            user_name = user_info.get('ingame_name', 'Guest') or 'Guest'
            user_balance = user_info.get('balance', 0) or 0
            user_wins = user_info.get('wins', 0) or 0

        # 3. প্রম্পট তৈরি (System Prompt - উন্নত)
        system_prompt = f'''আপনি 'eFootball Tournament Bot' এর একজন AI Admin।
ভাষা: বাংলা (Bangla)।
উত্তর ছোট, বন্ধুত্বপূর্ণ এবং সহায়ক রাখুন (৫০-১০০ শব্দের মধ্যে)।

বট তথ্য:
- নাম: {config.BOT_USERNAME}
- Bkash/Nagad: {config.BKASH_NUMBER}
- ন্যূনতম ডিপোজিট: {config.MINIMUM_DEPOSIT} TK
- ন্যূনতম প্রত্যাহার: {config.MINIMUM_WITHDRAWAL} TK

নিয়মাবলী:
{rules}

ব্যবহারকারী তথ্য:
- নাম: {user_name}
- ব্যালেন্স: {user_balance:.2f} TK
- বিজয়: {user_wins}

নির্দেশনা:
1. সর্বদা বাংলায় উত্তর দিন
2. শুধুমাত্র eFootball এবং বটের বৈশিষ্ট্য সম্পর্কে কথা বলুন
3. টাকার সমস্যা নিয়ে আসলে সরাসরি অ্যাডমিনদের সাথে যোগাযোগ করতে বলুন
4. অবশ্যই বন্ধুত্বপূর্ণ এবং পেশাদার থাকুন'''

        # 4. Groq API রিকোয়েস্ট
        url = "https://api.groq.com/openai/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {config.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "mixtral-8x7b-32768",  # Groq এর দ্রুত মডেল
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query[:500]}  # 500 অক্ষর সীমা
            ],
            "temperature": 0.7,
            "max_tokens": 256,  # আরো ছোট রেসপন্স
            "top_p": 0.95
        }

        # 5. রিকোয়েস্ট পাঠানো
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=config.REQUEST_TIMEOUT
                )
            ),
            timeout=config.REQUEST_TIMEOUT + 5
        )

        if response.status_code == 200:
            data = response.json()
            ai_response = data['choices'][0]['message']['content'].strip()

            # ছোট করুন যদি প্রয়োজন হয়
            if len(ai_response) > 500:
                ai_response = ai_response[:497] + '...'

            return ai_response
        elif response.status_code == 429 and retry_count < MAX_RETRIES:
            # Rate limited - retry করুন
            logger.warning(f"Rate limited, retrying... (attempt {retry_count + 1})")
            await asyncio.sleep(RETRY_DELAY * (retry_count + 1))
            return await get_ai_response(user_query, user_info, retry_count + 1)
        else:
            logger.error(f"Groq API Error: {response.status_code} - {response.text[:200]}")
            return "সার্ভারে একটু সমস্যা হয়েছে। পরে আবার চেষ্টা করুন।"

    except asyncio.TimeoutError:
        logger.error("Groq API Request Timeout")
        return "রিকোয়েস্ট সময়মতো রেসপন্স দেয়নি। পরে চেষ্টা করুন।"
    except requests.exceptions.ConnectionError:
        logger.error("Network Connection Error")
        return "ইন্টারনেট সংযোগে সমস্যা। আপনার নেটওয়ার্ক চেক করুন।"
    except requests.exceptions.Timeout:
        logger.error("Request Timeout")
        return "সময় শেষ হয়ে গেছে। পরে আবার চেষ্টা করুন।"
    except (json.JSONDecodeError, KeyError):
        logger.error("Invalid JSON Response from Groq API")
        return "API রেসপন্স ত্রুটিপূর্ণ। আবার চেষ্টা করুন।"
    except Exception as e:
        logger.error(f"Unexpected Error in AI Response: {e}", exc_info=True)
        return "একটি অপ্রত্যাশিত ত্রুটি হয়েছে। অনুগ্রহ করে পরে চেষ্টা করুন।"

