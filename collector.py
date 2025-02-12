import logging
import asyncio
import aiosqlite
import aiohttp
import json
import time

DB_FILE = "fuel_data.db"
CONFIG_FILE = "stations.json"

# Порог для микроизменений (если разница меньше MICRO_THRESHOLD, изменения не считаются значимыми)
MICRO_THRESHOLD = 0.02
# Количество циклов, в течение которых изменение должно подтверждаться, чтобы считаться стабильным
REQUIRED_STABLE_CYCLES = 2

# Глобальный словарь для хранения debounce-данных по каждой станции (ключ – station_id)
# Структура: { station_id: { "prev_record": dict, "counter": int, "pending_record": dict } }
debounce_data = {}

async def init_db():
    """Создает базу данных и необходимые таблицы, если они еще не существуют."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                city TEXT NOT NULL,
                postal_code TEXT NOT NULL,
                station_api TEXT NOT NULL UNIQUE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fuel_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER,
                timestamp INTEGER NOT NULL,
                diesel REAL,
                e10 REAL,
                super REAL,
                FOREIGN KEY (station_id) REFERENCES stations(id)
            )
        """)
        await db.commit()
        logging.info("База данных создана или уже существует.")

async def load_stations():
    """Загружает список заправок из файла CONFIG_FILE."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            stations = json.load(file)
        return stations
    except Exception as e:
        logging.error(f"Ошибка загрузки {CONFIG_FILE}: {e}")
        return []

async def fetch_prices(station_api):
    """Асинхронно получает цены на топливо с API заправки."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(station_api) as response:
                response.raise_for_status()
                return await response.json()
    except Exception as e:
        logging.error(f"Ошибка запроса к API {station_api}: {e}")
        return None

async def get_or_create_station(db, station):
    """
    Проверяет, есть ли запись о заправке в таблице stations по station_api.
    Если нет, автоматически создает новую запись, используя данные из файла.
    Возвращает id записи (station_id).
    """
    async with db.execute("SELECT id FROM stations WHERE station_api = ?", (station["api_url"],)) as cursor:
        row = await cursor.fetchone()
    if row:
        return row[0]
    else:
        await db.execute("""
            INSERT INTO stations (name, city, postal_code, station_api)
            VALUES (?, ?, ?, ?)
        """, (station["name"], station["city"], station["postal_code"], station["api_url"]))
        await db.commit()
        async with db.execute("SELECT id FROM stations WHERE station_api = ?", (station["api_url"],)) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else None

async def get_last_record(db, station_id):
    """
    Возвращает последнюю запись из таблицы fuel_prices для заданной заправки.
    """
    async with db.execute("""
        SELECT timestamp, diesel, e10, super
        FROM fuel_prices
        WHERE station_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (station_id,)) as cursor:
        row = await cursor.fetchone()
        if row:
            return {
                "timestamp": row[0],
                "diesel": row[1],
                "e10": row[2],
                "super": row[3]
            }
        return None

async def insert_prices(db, station_id, prices):
    """Сохраняет данные о ценах на топливо в таблицу fuel_prices."""
    timestamp = int(time.time())
    await db.execute("""
        INSERT INTO fuel_prices (station_id, timestamp, diesel, e10, super)
        VALUES (?, ?, ?, ?, ?)
    """, (station_id, timestamp, prices.get("diesel"), prices.get("e10"), prices.get("super")))
    await db.commit()
    logging.info(f"Цены успешно сохранены для станции с id: {station_id}")

def prices_differ(new_prices, old_prices):
    """
    Возвращает True, если для хотя бы одного вида топлива разница между new_prices и old_prices\n
    превышает MICRO_THRESHOLD.
    """
    for fuel in ["diesel", "e10", "super"]:
        if abs(new_prices.get(fuel, 0) - old_prices.get(fuel, 0)) >= MICRO_THRESHOLD:
            return True
    return False

async def collect_data():
    """Обходит все заправки, опрашивает их API и сохраняет данные в базу с фильтрацией микроизменений."""
    stations = await load_stations()
    if not stations:
        logging.error("Нет доступных заправок для опроса.")
        return

    async with aiosqlite.connect(DB_FILE) as db:
        for station in stations:
            station_id = await get_or_create_station(db, station)
            if not station_id:
                logging.warning(f"Не удалось получить или создать запись для заправки {station['name']}, пропускаем...")
                continue

            prices = await fetch_prices(station["api_url"])
            if not prices:
                logging.error(f"Не удалось получить цены с API для станции {station['name']}.")
                continue

            logging.info(f"Получены цены для {station['name']} ({station['city']}): {prices}")
            # Пропускаем запись, если все цены равны 0.0
            if all(price == 0.0 for price in prices.values()):
                logging.info("Получены цены со значением 0.0, запись в базу данных пропущена.")
                continue

            # Получаем последнюю запись для данной заправки
            last_record = await get_last_record(db, station_id)
            if not last_record:
                # Если записи нет, вставляем данные сразу
                await insert_prices(db, station_id, prices)
                debounce_data[station_id] = {
                    "prev_record": prices,
                    "counter": 1,
                    "pending_record": prices
                }
            else:
                # Если новые цены существенно отличаются от последней записи
                if prices_differ(prices, last_record):
                    # Инициализируем или обновляем debounce-данные для данной станции
                    if station_id not in debounce_data:
                        debounce_data[station_id] = {
                            "prev_record": last_record,
                            "counter": 1,
                            "pending_record": prices
                        }
                    else:
                        if prices == debounce_data[station_id]["pending_record"]:
                            debounce_data[station_id]["counter"] += 1
                        else:
                            debounce_data[station_id]["pending_record"] = prices
                            debounce_data[station_id]["counter"] = 1
                    logging.info(f"Для заправки {station['name']} обнаружено изменение. Счетчик: {debounce_data[station_id]['counter']}/{REQUIRED_STABLE_CYCLES}")
                    if debounce_data[station_id]["counter"] >= REQUIRED_STABLE_CYCLES:
                        await insert_prices(db, station_id, prices)
                        logging.info(f"Изменения подтверждены для заправки {station['name']}. Новые цены сохранены.")
                        debounce_data[station_id]["prev_record"] = prices
                        debounce_data[station_id]["counter"] = 0
                        debounce_data[station_id]["pending_record"] = None
                else:
                    logging.info(f"Для заправки {station['name']} изменений не обнаружено.")
                    # Обновляем сохраненные данные, если изменений нет
                    if station_id in debounce_data:
                        debounce_data[station_id]["prev_record"] = prices
                        debounce_data[station_id]["counter"] = 0
                        debounce_data[station_id]["pending_record"] = None

async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    await init_db()
    while True:
        await collect_data()
        await asyncio.sleep(300)  # Опрашивать API каждую минуту

if __name__ == "__main__":
    asyncio.run(main())
