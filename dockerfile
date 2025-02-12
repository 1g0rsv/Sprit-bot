# Используем официальный образ Python (например, 3.10-slim)
FROM python:3.10-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл requirements.txt и устанавливаем зависимости
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Копируем необходимые файлы приложения в рабочую директорию
COPY sprit-bot-app-v1.04.py /app/sprit-bot-app.py
COPY collector.py /app/collector.py
COPY stations.json /app/

# По умолчанию задаём запуск бота (этот CMD можно переопределить в docker-compose)
CMD ["python", "sprit-bot-app.py"]