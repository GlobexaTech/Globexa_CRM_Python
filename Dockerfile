FROM python:3.11-slim AS builder
WORKDIR /src
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip setuptools && pip wheel --wheel-dir /wheels .

FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 APP_ENVIRONMENT=production APP_DEBUG=false
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels globexa-crm && rm -rf /wheels \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
COPY config.yaml alembic.ini ./
COPY alembic ./alembic
COPY scripts/provision_runtime.py ./scripts/provision_runtime.py
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
