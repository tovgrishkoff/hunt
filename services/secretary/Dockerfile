FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Установка OpenAI (если еще не в requirements.txt)
RUN pip install --no-cache-dir openai || echo "OpenAI already installed"

# Копирование общих модулей
COPY shared/ /app/shared/

# Копирование структуры services
COPY services/ /app/services/

# Копирование конфигурации
COPY config/ /app/config/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Запуск из директории сервиса
WORKDIR /app/services/secretary

CMD ["python", "main.py"]

