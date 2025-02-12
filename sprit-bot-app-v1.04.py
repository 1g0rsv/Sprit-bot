import os
import logging
import asyncio
import aiosqlite
import nest_asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

nest_asyncio.apply()

DB_FILE = "fuel_data.db"
BOT_TOKEN = os.getenv("BOT_TOKEN")

required_stable_cycles = 2  # Количество циклов для подтверждения изменений
debounce_data = {}

async def get_latest_records():
    """
    Извлекает последнюю запись для каждой станции.
    Возвращает словарь: {station_id: {record}}
    """
    async with aiosqlite.connect(DB_FILE) as conn:
        query = """
        SELECT fp.timestamp, fp.diesel, fp.e10, fp.super,
               s.id as station_id, s.postal_code, s.city, s.name as station_name, s.station_api
        FROM fuel_prices fp
        JOIN stations s ON fp.station_id = s.id
        ORDER BY fp.timestamp DESC
        """
        async with conn.execute(query) as cursor:
            rows = await cursor.fetchall()
            records = {}
            for row in rows:
                station_id = row[4]
                if station_id not in records:
                    records[station_id] = {
                        "timestamp": row[0],
                        "diesel": row[1],
                        "e10": row[2],
                        "super": row[3],
                        "postal_code": row[5],
                        "city": row[6],
                        "station_name": row[7],
                        "station_api": row[8]
                    }
            return records

def format_record_message(record):
    import datetime
    dt = datetime.datetime.fromtimestamp(record["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
    message = (f"Aktualisierte Preise (zum {dt}) für die Tankstelle {record['station_name']} "
               f"({record['city']}, {record['postal_code']}):\n"
               f"Diesel: {record['diesel']}\n"
               f"E10: {record['e10']}\n"
               f"Super: {record['super']}")
    return message

async def get_subscribers():
    SUBSCRIBERS_DB = "subscribers.db"
    async with aiosqlite.connect(SUBSCRIBERS_DB) as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY
            )
        ''')
        await conn.commit()
        async with conn.execute("SELECT chat_id FROM subscribers") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def add_subscriber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    SUBSCRIBERS_DB = "subscribers.db"
    async with aiosqlite.connect(SUBSCRIBERS_DB) as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY
            )
        ''')
        try:
            await conn.execute("INSERT INTO subscribers (chat_id) VALUES (?)", (chat_id,))
            await conn.commit()
            logging.info(f"Подписчик {chat_id} добавлен.")
        except aiosqlite.IntegrityError:
            logging.info(f"Подписчик {chat_id} уже существует.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /start:
    - Добавляет пользователя в базу подписчиков.
    - Отправляет приветственное сообщение.
    - Извлекает из базы последние актуальные данные по заправкам и отправляет их пользователю.
    """
    await add_subscriber(update, context)
    await update.message.reply_text("Sie haben die Updates abonniert!")
    logging.info(f"/start получен от chat_id: {update.effective_chat.id}")

    # Извлекаем последние данные из базы
    records = await get_latest_records()
    if records:
        messages = []
        for station_id, record in records.items():
            messages.append(format_record_message(record))
        combined_message = "\n\n".join(messages)
        try:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=combined_message)
            logging.info(f"Отправлены актуальные цены новому подписчику {update.effective_chat.id}.")
        except Exception as e:
            logging.error(f"Ошибка отправки актуальных цен пользователю {update.effective_chat.id}: {e}")
    else:
        try:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Нет актуальных данных о ценах.")
            logging.info("Нет данных для отправки актуальных цен новому подписчику.")
        except Exception as e:
            logging.error(f"Ошибка отправки сообщения о пустых данных пользователю {update.effective_chat.id}: {e}")

async def send_update(context: ContextTypes.DEFAULT_TYPE):
    global debounce_data
    records = await get_latest_records()
    if not records:
        logging.info("Нет данных в базе для обновления.")
        return

    subscribers = await get_subscribers()
    for station_id, current_record in records.items():
        current_message = format_record_message(current_record)
        if station_id not in debounce_data:
            debounce_data[station_id] = {
                "prev_record": current_record,
                "counter": 1,
                "pending_record": current_message
            }
            logging.info(f"Новая станция {current_record['station_name']}: отправляем первоначальное уведомление.")
            for chat_id in subscribers:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=current_message)
                    logging.info(f"Первоначальное уведомление отправлено для станции {current_record['station_name']} пользователю {chat_id}.")
                except Exception as e:
                    logging.error(f"Ошибка отправки уведомления пользователю {chat_id}: {e}")
            continue

        prev_data = debounce_data[station_id]
        prev_record = prev_data["prev_record"]
        change_detected = any(current_record[fuel] != prev_record[fuel] for fuel in ["diesel", "e10", "super"])

        if change_detected:
            if current_message == prev_data["pending_record"]:
                prev_data["counter"] += 1
            else:
                prev_data["pending_record"] = current_message
                prev_data["counter"] = 1

            logging.info("Для станции %s обнаружено изменение, счетчик: %d/%d.",
                         current_record["station_name"], prev_data["counter"], required_stable_cycles)
            if prev_data["counter"] >= required_stable_cycles:
                logging.info("Изменения стабилизировались для станции %s, отправляем уведомление.",
                             current_record["station_name"])
                for chat_id in subscribers:
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=current_message)
                        logging.info(f"Уведомление отправлено для станции {current_record['station_name']} пользователю {chat_id}.")
                    except Exception as e:
                        logging.error(f"Ошибка отправки уведомления пользователю {chat_id}: {e}")
                debounce_data[station_id]["prev_record"] = current_record
                debounce_data[station_id]["counter"] = 0
                debounce_data[station_id]["pending_record"] = None
            else:
                logging.info("Изменение для станции %s пока не стабилизировалось, уведомление не отправлено.",
                             current_record["station_name"])
        else:
            logging.info("Для станции %s изменений не обнаружено.", current_record["station_name"])
            debounce_data[station_id]["prev_record"] = current_record
            debounce_data[station_id]["counter"] = 0
            debounce_data[station_id]["pending_record"] = None

async def main():
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    # Планируем периодическую отправку уведомлений каждые 5 минут (300 секунд)
    app.job_queue.run_repeating(send_update, interval=300, first=10)
    logging.info("Бот успешно запущен и начинает работу!")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())