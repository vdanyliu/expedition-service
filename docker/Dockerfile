FROM python:3.13-slim


ENV PYTHONUNBUFFERED=1 \
    UVICORN_OPTS='' \
    SERVICE_PORT=8080

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir uv \
 && uv pip install --system -e .

COPY . .

EXPOSE ${SERVICE_PORT}

CMD uvicorn run_local:app ${UVICORN_OPTS} --host 0.0.0.0 --port ${SERVICE_PORT}
