FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/  bot/
COPY utils/ utils/
COPY VERSION VERSION

RUN mkdir -p data

CMD ["python", "-m", "bot.main"]
