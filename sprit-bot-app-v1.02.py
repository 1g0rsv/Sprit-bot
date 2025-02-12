import logging
import asyncio
import aiosqlite
import nest_asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

nest_asyncio.apply()

DB_FILE = "fuel_data.db"
BOT_TOKEN = "7352620616:AAGeAssByHbN2GlpBXsQq1Ngao2-Ix_LG44"
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
    message = (f"Aktualisierte Preise  (zum {dt}) für die Tankstelle {record['station_name']} "
               f"({record['city']}, {record['postal_code']}):\n"
               f"Diesel: {record['diesel']}\n"
               f"E10: {record['e10']}\n"
               f"Super: {record['super']}")
    return message

async def get_subscribers():
    SUBSCRIBERS_DB = "subscribers.db"
    async with aiosqlite.connect(SUBSCRIBERS_DB) as conn:
        async with conn.execute("SELECT chat_id FROM subscribers") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Регистрирует пользователя для получения обновлений."""
    chat_id = update.effective_chat.id
    SUBSCRIBERS_DB = "subscribers.db"
    async with aiosqlite.connect(SUBSCRIBERS_DB) as conn:
        try:
            await conn.execute("INSERT INTO subscribers (chat_id) VALUES (?)", (chat_id,))
            await conn.commit()
            logging.info(f"Подписчик {chat_id} добавлен.")
        except aiosqlite.IntegrityError:
            logging.info(f"Подписчик {chat_id} уже существует.")
    await update.message.reply_text("Sie haben die Updates abonniert!")

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
                "stable_counter": 1,
                "last_message": current_message
            }
            logging.info(f"Новое сообщение отправлено сразу: {current_message}")
            for chat_id in subscribers:
                await context.bot.send_message(chat_id=chat_id, text=current_message)
            continue

        prev_data = debounce_data[station_id]
        prev_record = prev_data["prev_record"]
        change_detected = any(current_record[fuel] != prev_record[fuel] for fuel in ["diesel", "e10", "super"])

        if change_detected:
            prev_data["stable_counter"] += 1 if current_message == prev_data["last_message"] else 1
            prev_data["last_message"] = current_message
            
            logging.info(f"Изменение зафиксировано для {current_record['station_name']}, счетчик: {prev_data['stable_counter']}/{required_stable_cycles}")
            
            if prev_data["stable_counter"] >= required_stable_cycles:
                logging.info(f"Цены стабилизировались, отправляем сообщение: {current_message}")
                for chat_id in subscribers:
                    await context.bot.send_message(chat_id=chat_id, text=current_message)
                debounce_data[station_id] = {"prev_record": current_record, "stable_counter": 0, "last_message": None}
        else:
            logging.info(f"Изменений для {current_record['station_name']} нет.")

async def main():
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.job_queue.run_repeating(send_update, interval=300, first=10)
    logging.info("Бот запущен и ожидает обновлений.")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())