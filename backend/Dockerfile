FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Runtime dependencies only. Installing the dev extras would drag pytest, ruff,
# mypy and the whole database stack into a production image that never uses them.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt uvicorn[standard]

COPY app ./app

EXPOSE 8000

# Container hosts inject $PORT and health-check against it. Hardcoding 8000 makes
# the deploy fail in a way that looks like a broken app rather than a bound port.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
