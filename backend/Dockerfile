# One image for the API, the worker and the mock service (they differ only in the command).
# Build from the repo root:  docker build -f backend/Dockerfile -t hiintegrate-backend .
# The code finds schema/ and templates/ relative to the repo root, so the layout is kept:
#   /app/backend  /app/schema  /app/templates
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app/backend

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/backend/
COPY schema/integration.schema.json schema/result.schema.json /app/schema/
COPY templates/ /app/templates/

# Run as a normal user, not root.
RUN useradd --create-home --uid 1000 app && chown -R app /app
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
