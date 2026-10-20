FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home \
        --shell /usr/sbin/nologin app \
    && chmod +x /app/entrypoint.sh

USER app:app

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
