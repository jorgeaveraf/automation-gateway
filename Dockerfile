FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY automation_gateway ./automation_gateway
COPY README.md .
COPY deploy/docker-compose.production.yml ./deploy/docker-compose.production.yml

RUN addgroup --system automation \
    && adduser --system --ingroup automation --no-create-home automation \
    && chown -R automation:automation /app

USER automation

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"]

CMD ["uvicorn", "automation_gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
