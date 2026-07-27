"""Celery application for durable Gmail synchronization work."""

from celery import Celery

from arcis_backend.settings import get_settings

settings = get_settings()
celery_app = Celery("arcis", broker=settings.redis_url, backend=settings.redis_url, include=["arcis_backend.tasks"])
celery_app.conf.update(
    timezone="Asia/Kolkata",
    beat_schedule={"daily-gmail-sync": {"task": "arcis.gmail.enqueue_daily", "schedule": 24 * 60 * 60}},
)
