# Ensure the Celery app is loaded when Django starts, so the shared_task
# decorator uses the configured app. See config/celery.py for the bootstrap.
from .celery import app as celery_app

__all__ = ("celery_app",)
