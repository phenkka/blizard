FROM python:3.11-alpine

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование всего приложения
COPY . .

# Создание non-root пользователя
RUN addgroup -g 1001 -S python
RUN adduser -S python -u 1001

# Смена владельца директории
RUN chown -R python:python /app
USER python

EXPOSE 3000

# Запуск приложения - бэкенд будет отдавать статику фронтенда
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]
