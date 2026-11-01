# The demo mock service: the project's own mock (D-9) plus an HR system with fixable bad records. Build from the REPO ROOT (the compose overlay does this):
#   docker build -f present/mock_api/Dockerfile -t hiintegrate-demo-mock .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv

RUN pip install --no-cache-dir "fastapi>=0.115,<1" "uvicorn[standard]>=0.30,<1"

# The original mock is reused unchanged, so scripts/rehearse.py still passes against this image.
COPY backend/tests/mock_api/app.py /srv/base_app.py
COPY present/mock_api/demo_app.py /srv/demo_app.py

RUN useradd --create-home --uid 1000 app && chown -R app /srv
USER app

EXPOSE 8001
CMD ["uvicorn", "demo_app:app", "--host", "0.0.0.0", "--port", "8001"]
