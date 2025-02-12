import time
import requests
import logging
from telegram import Bot

# Задайте свой токен и chat_id
BOT_TOKEN = "7352620616:AAGeAssByHbN2GlpBXsQq1Ngao2-Ix_LG44"  # Замените на токен вашего бота
CHAT_ID = "328852789"              # Замените на ваш chat_id

bot = Bot(token=BOT_TOKEN)

# URL эндпоинта с данными о топливе
URL = "http://localhost:5001/details/64295-darmstadt-shell/1202262118/"

# Переменная для хранения предыдущих значений цен
prev_prices = None

def fetch_prices():
    """
    Получает данные с эндпоинта и возвращает JSON с ценами.
    """
    try:
        response = requests.get(URL)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error("Ошибка запроса к API: %s", e)
        return None

def compare_and_notify(current, previous):
    """
    Сравнивает два словаря с ценами и отправляет уведомление в Telegram,
    если найдены изменения.
    """
    changes = []
    for fuel_type, current_price in current.items():
        previous_price = previous.get(fuel_type)
        # Если цены отличаются, формируем сообщение об изменении
        if previous_price is not None and current_price != previous_price:
            changes.append(f"{fuel_type}: {previous_price} -> {current_price}")
    
    if changes:
        message = "Обнаружены изменения цен на топливо:\n" + "\n".join(changes)
        try:
            bot.send_message(chat_id=CHAT_ID, text=message)
            logging.info("Уведомление отправлено: %s", message)
        except Exception as e:
            logging.error("Ошибка отправки сообщения: %s", e)

def main():
    global prev_prices
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Первоначальное получение цен
    prev_prices = fetch_prices()
    if prev_prices:
        logging.info("Начальные цены: %s", prev_prices)
    else:
        logging.error("Не удалось получить начальные цены!")
    
    while True:
        time.sleep(3600)  # Ждем 1 час (3600 секунд)
        current_prices = fetch_prices()
        if current_prices:
            # Если предыдущие цены существуют, сравниваем их с новыми
            if prev_prices:
                if current_prices != prev_prices:
                    compare_and_notify(current_prices, prev_prices)
                else:
                    logging.info("Изменений не обнаружено.")
            # Обновляем сохранённые цены
            prev_prices = current_prices

if __name__ == "__main__":
    main()