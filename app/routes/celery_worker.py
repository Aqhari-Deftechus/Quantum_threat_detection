# celery_worker.py
from celery_tasks import celery_app

# Nothing else required here.
# This file simply exposes celery_app so Celery worker can use it.

# Command to start worker:
# celery -A celery_worker.celery_app worker -P eventlet --loglevel=info
