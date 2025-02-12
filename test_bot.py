import logging
from telegram import Bot

# Замените значения ниже на свои реальные данные
BOT_TOKEN = "7352620616:AAGeAssByHbN2GlpBXsQq1Ngao2-Ix_LG44"  # Токен, полученный у BotFather
CHAT_ID = "328852789"              # Ваш Chat ID, куда отправлять сообщение

def main():
    # Настройка логирования для удобства отладки
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    bot = Bot(token=BOT_TOKEN)
    
    try:
        # Отправка тестового сообщения
        bot.send_message(chat_id=CHAT_ID, text="Тестовое сообщение от Telegram-бота!")
        logging.info("Сообщение успешно отправлено!")
    except Exception as e:
        logging.error("Ошибка при отправке сообщения: %s", e)

if __name__ == "__main__":
    main()