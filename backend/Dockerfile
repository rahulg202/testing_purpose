FROM python:3.11-slim AS builder

WORKDIR /app

# Install build deps
RUN pip install --no-cache-dir build setuptools wheel

# Copy packages first for layer caching
COPY packages/ packages/
RUN pip install --no-cache-dir packages/atheria-contracts packages/atheria-llm

# Copy backend
COPY pyproject.toml .
COPY backend/ backend/
RUN pip install --no-cache-dir .

# --- Runtime stage ---
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY backend/ backend/
COPY packages/ packages/

# Non-root user
RUN useradd -m -r atheria && chown -R atheria:atheria /app
USER atheria

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
