import logging
import asyncio
import aiosqlite
import nest_asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Применяем патч для вложенных event loop (если запускаем в интерактивном режиме или некоторых IDE)
nest_asyncio.apply()

# Файл базы данных для измерений (предполагается, что он заполняется collector.py)
DB_FILE = "fuel_prices.db"
# Файл базы данных для подписчиков (если используется отдельная база; можно использовать ту же)
SUBSCRIBERS_DB = "subscribers.db"

# Токен вашего бота (замените на ваш)
BOT_TOKEN = "7352620616:AAGeAssByHbN2GlpBXsQq1Ngao2-Ix_LG44"

# Глобальные переменные для хранения предыдущего (последнего) полученного набора цен
prev_record = None
stable_change_counter = 0
required_stable_cycles = 2  # Количество циклов, в течение которых изменение должно подтверждаться
last_pending_message = None

async def get_latest_prices():
    """
    Извлекает из базы данных fuel_prices последнюю запись по времени.
    Предполагается, что таблица fuel_prices имеет поля: timestamp, diesel, e10, super, station_id.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT timestamp, diesel, e10, super, station_id FROM fuel_prices ORDER BY timestamp DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "timestamp": row[0],
                    "diesel": row[1],
                    "e10": row[2],
                    "super": row[3],
                    "station_id": row[4]
                }
            else:
                return None

def format_prices_message(prices):
    """
    Форматирует данные о ценах в читаемое сообщение.
    """
    import datetime
    dt = datetime.datetime.fromtimestamp(prices["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
    message = (f"Обновленные цены (на {dt}):\n"
               f"Diesel: {prices['diesel']}\n"
               f"E10: {prices['e10']}\n"
               f"Super: {prices['super']}")
    return message

async def add_subscriber(chat_id: int):
    """
    Добавляет нового подписчика (chat_id) в базу данных подписчиков.
    Создаётся таблица subscribers, если её еще нет.
    """
    async with aiosqlite.connect(SUBSCRIBERS_DB) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY
            )
        ''')
        try:
            await db.execute("INSERT INTO subscribers (chat_id) VALUES (?)", (chat_id,))
            await db.commit()
            logging.info(f"Подписчик {chat_id} добавлен.")
        except aiosqlite.IntegrityError:
            logging.info(f"Подписчик {chat_id} уже существует.")

async def get_subscribers():
    """
    Возвращает список chat_id всех подписчиков из базы данных подписчиков.
    """
    async with aiosqlite.connect(SUBSCRIBERS_DB) as db:
        async with db.execute("SELECT chat_id FROM subscribers") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /start: сохраняет chat_id пользователя и отправляет приветственное сообщение.
    """
    chat_id = update.effective_chat.id
    await add_subscriber(chat_id)
    await update.message.reply_text("Вы подписались на обновления!")
    logging.info(f"/start получен от chat_id: {chat_id}")

async def send_update(context: ContextTypes.DEFAULT_TYPE):
    """
    Периодическая функция, которая извлекает последние данные о ценах из базы и, если изменения подтверждены,
    отправляет уведомление подписчикам.
    Механизм debounce: уведомление отправляется только если новое сообщение стабильно (подтверждено требуемым количеством циклов).
    """
    global prev_record, stable_change_counter, last_pending_message

    current_record = await get_latest_prices()
    if not current_record:
        logging.info("Нет данных в таблице fuel_prices для обновления.")
        return

    current_message = format_prices_message(current_record)
    logging.debug("Текущее сообщение: %s", current_message)

    # Если предыдущая запись отсутствует, устанавливаем ее и отправляем уведомление
    if prev_record is None:
        prev_record = current_record
        stable_change_counter = 1
        last_pending_message = current_message
        subscribers = await get_subscribers()
        for chat_id in subscribers:
            try:
                await context.bot.send_message(chat_id=chat_id, text=current_message)
                logging.info(f"Сообщение отправлено пользователю {chat_id}")
            except Exception as e:
                logging.error(f"Ошибка отправки сообщения пользователю {chat_id}: {e}")
        return

    # Сравниваем текущие цены с предыдущими (для diesel, e10, super)
    changed = False
    for fuel in ["diesel", "e10", "super"]:
        if current_record[fuel] != prev_record[fuel]:
            changed = True
            break

    if changed:
        # Если новое сообщение совпадает с предыдущим ожидаемым, увеличиваем счетчик
        if current_message == last_pending_message:
            stable_change_counter += 1
        else:
            stable_change_counter = 1
            last_pending_message = current_message

        logging.info("Изменение зафиксировано, ожидаем подтверждения (счетчик %d/%d).",
                     stable_change_counter, required_stable_cycles)
        # Если изменение стабильно в течение требуемого количества циклов, отправляем уведомление
        if stable_change_counter >= required_stable_cycles:
            subscribers = await get_subscribers()
            for chat_id in subscribers:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=current_message)
                    logging.info(f"Обновление отправлено пользователю {chat_id}")
                except Exception as e:
                    logging.error(f"Ошибка отправки обновления пользователю {chat_id}: {e}")
            prev_record = current_record
            stable_change_counter = 0
            last_pending_message = None
    else:
        logging.info("Изменений не обнаружено.")
        prev_record = current_record
        stable_change_counter = 0
        last_pending_message = None

async def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    # Создаем Telegram-приложение
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    # Планируем периодическую отправку обновлений.
    # Здесь интервал установлен в 300 секунд (5 минут) для демонстрации; его можно изменить по необходимости.
    app.job_queue.run_repeating(send_update, interval=300, first=10)
    
    logging.info("Бот успешно запущен и начинает работу!")
    await app.run_polling()

if __name__ == '__main__':
    # Используем существующий event loop, чтобы избежать ошибки "This event loop is already running"
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
