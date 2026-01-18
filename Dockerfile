FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Python зависимости
# 1. Сначала ставим легкий PyTorch (CPU version) - это важно!
# Если установить torch после sentence-transformers, он может скачать тяжелую GPU-версию (~4 Гб)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# 2. Потом sentence-transformers (он увидит, что torch уже есть, и не будет качать тяжелый)
RUN pip install --no-cache-dir sentence-transformers numpy

# 3. Остальные зависимости
RUN pip install --no-cache-dir \
    asyncpg \
    python-dotenv \
    requests \
    "aiogram==2.25.1" \
    aiohttp \
    telethon \
    openai

# Создаем директории для логов и данных
RUN mkdir -p /app/logs /app/data

# Устанавливаем переменные окружения
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Команда по умолчанию (может быть переопределена в docker-compose.yml)
CMD ["python", "--version"]

