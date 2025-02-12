#!/bin/bash
# start.sh: запускаем collector и sprit-bot одновременно

# Запускаем collector в фоне
python collector.py &
COLLECTOR_PID=$!

# Запускаем Telegram-бот в фоне
python sprit-bot-app.py &
BOT_PID=$!

# Ждем завершения обоих процессов
wait $COLLECTOR_PID $BOT_PID