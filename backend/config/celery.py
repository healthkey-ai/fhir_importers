"""
Celery application bootstrap.

Phase 0: no tasks defined yet — this file exists so the worker service can
boot and register with the broker before the FHIR sync pipeline lands in
Phase 2. Tasks are auto-discovered from any installed app's `tasks.py`.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("fhir_importers")

# Pulls all settings starting with CELERY_ from Django settings
app.config_from_object("django.conf:settings", namespace="CELERY")

# Find tasks.py in any INSTALLED_APPS module
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Smoke test task. `celery -A config call config.celery.debug_task`."""
    print(f"Celery debug task fired — request: {self.request!r}")
