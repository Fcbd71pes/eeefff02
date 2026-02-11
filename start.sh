#!/bin/bash

# eFootball Tournament Bot - Termux Start Script (Enhanced)
# এই স্ক্রিপ্টটি Termux এ বট চালানোর জন্য

set -e  # Exit on error

echo "=========================================="
echo "   eFootball Tournament Bot Launcher"
echo "=========================================="
echo ""

# Termux পাথ সেটিংস
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# রঙ সংজ্ঞা (আউটপুটের জন্য)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'  # No Color

# লগ ফাইল
LOG_DIR="${HOME}/.eFootball_bot/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/start_$(date +%Y%m%d_%H%M%S).log"

echo -e "${BLUE}[*] Log file: $LOG_FILE${NC}"
echo "" | tee -a "$LOG_FILE"

# ১. Python ভার্সন চেক
echo -e "${BLUE}[*] Checking Python version...${NC}" | tee -a "$LOG_FILE"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[!] Python 3 is not installed!${NC}" | tee -a "$LOG_FILE"
    echo -e "${YELLOW}[*] Install with: pkg install python${NC}" | tee -a "$LOG_FILE"
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1)
echo -e "${GREEN}[+] $PYTHON_VERSION${NC}" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# ২. প্রয়োজনীয় প্যাকেজ চেক এবং ইনস্টল
echo -e "${BLUE}[*] Checking and installing required packages...${NC}" | tee -a "$LOG_FILE"
if ! python3 -m pip show python-telegram-bot &> /dev/null; then
    echo -e "${YELLOW}[*] Installing packages from requirements.txt...${NC}" | tee -a "$LOG_FILE"
    if ! python3 -m pip install -r requirements.txt 2>&1 | tee -a "$LOG_FILE"; then
        echo -e "${RED}[!] Failed to install packages!${NC}" | tee -a "$LOG_FILE"
        exit 1
    fi
else
    echo -e "${GREEN}[+] Required packages are already installed${NC}" | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# ৩. Token চেক
echo -e "${BLUE}[*] Checking configuration...${NC}" | tee -a "$LOG_FILE"
if [ -z "$BOT_TOKEN" ] && ! grep -q "BOT_TOKEN" config.py; then
    echo -e "${YELLOW}[!] Warning: BOT_TOKEN not found in environment or config.py${NC}" | tee -a "$LOG_FILE"
fi
echo -e "${GREEN}[+] Configuration checked${NC}" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# ৪. ডাটাবেস চেক
echo -e "${BLUE}[*] Checking database setup...${NC}" | tee -a "$LOG_FILE"
if python3 -c "import db; db.init_db()" 2>&1 | tee -a "$LOG_FILE"; then
    echo -e "${GREEN}[+] Database is ready${NC}" | tee -a "$LOG_FILE"
else
    echo -e "${YELLOW}[!] Database initialization warning (may be normal)${NC}" | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# ৫. বট স্টার্ট করা
echo "=========================================="
echo -e "${GREEN}[+] Starting eFootball Bot...${NC}" | tee -a "$LOG_FILE"
echo -e "${BLUE}[*] Main log: ~/.eFootball_bot/logs/bot.log${NC}" | tee -a "$LOG_FILE"
echo -e "${BLUE}[*] Start log: $LOG_FILE${NC}" | tee -a "$LOG_FILE"
echo "=========================================="
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the bot${NC}"
echo ""

# বট চালানো এবং ত্রুটি ধরা
if python3 "$SCRIPT_DIR/bot.py" 2>&1 | tee -a "$LOG_FILE"; then
    echo "" | tee -a "$LOG_FILE"
    echo -e "${GREEN}[+] Bot stopped gracefully${NC}" | tee -a "$LOG_FILE"
    exit 0
else
    EXIT_CODE=$?
    echo "" | tee -a "$LOG_FILE"
    echo -e "${RED}[!] Bot stopped with error code: $EXIT_CODE${NC}" | tee -a "$LOG_FILE"
    echo -e "${YELLOW}[*] Check logs for details:${NC}" | tee -a "$LOG_FILE"
    echo -e "${YELLOW}    - Main log: ~/.eFootball_bot/logs/bot.log${NC}" | tee -a "$LOG_FILE"
    echo -e "${YELLOW}    - Start log: $LOG_FILE${NC}" | tee -a "$LOG_FILE"
    exit $EXIT_CODE
fi
