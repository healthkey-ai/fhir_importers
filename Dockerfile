# HealthKey FHIR connector — Django service (GCP Cloud Run target).
# Phase 0: backend only. The Module Federation frontend remote is wired in
# Phase 1 (mirroring hk-labs' two-stage build at that point).
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

RUN python manage.py collectstatic --noinput

RUN adduser --disabled-password --no-create-home appuser
USER appuser

EXPOSE 8080

CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "120"]
