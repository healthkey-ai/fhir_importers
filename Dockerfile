# HealthKey FHIR connector — Django service (GCP Cloud Run target).
#
# Stage 1 builds the Module Federation remote (remoteEntry.js + chunks); stage 2
# is the Django runtime, which serves that remote via WhiteNoise so the ht-phr
# host can load mychart_remote cross-origin.

# Stage 1: build the Module Federation remote
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build:remote

# Stage 2: Python runtime
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    PORT=8080

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Module Federation remote entry (remoteEntry.js + chunks) → served by WhiteNoise
COPY --from=frontend-build /app/frontend/dist/remote ./frontend_remote

RUN python manage.py collectstatic --noinput

RUN adduser --disabled-password --no-create-home appuser
USER appuser

EXPOSE 8080

CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "120"]
