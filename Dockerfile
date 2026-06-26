# Stage 1: build the Module Federation remote (mychart_remote/remoteEntry.js + chunks).
# Output ends up under /app/frontend/dist/remote/ and is copied into the runtime stage.
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend

# Install deps first (better layer caching when only source changes).
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Now bring in the rest of the frontend and produce the remote bundle.
COPY frontend/ ./
RUN npm run build:remote


# Stage 2: Python runtime — FastAPI + the federation bundle as static files.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ ./app/
COPY services/ ./services/
COPY cli/ ./cli/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini
COPY organizations.json ./organizations.json

# Federation remote bundle, served by FastAPI's StaticFiles at /remote.
# (See `remote_bundle_dir` in app/config.py and the mount in app/main.py.)
COPY --from=frontend-build /app/frontend/dist/remote /app/frontend_remote

RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin app \
    && chown -R app /app
USER app

EXPOSE 8000

# Migrations run in a separate `migrate` compose service via
# `docker compose run --rm migrate` during deploy. App container just serves.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
