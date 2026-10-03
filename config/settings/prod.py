import os
from celery.schedules import crontab
from .base import *

DEBUG = False

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",")
    if host.strip()
] + ["localhost", "127.0.0.1"]

# Nginx serves collected assets; hashed URLs invalidate browser/CDN caches.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
}
NGINX_MEDIA_ACCEL = True

# Persisted by Celery Beat's schedule file; exactly one Beat instance is used.
CELERY_BEAT_SCHEDULE = {
    "end-expired-memberships": {
        "task": "apps.members.tasks.task_end_expired_memberships",
        "schedule": crontab(hour=0, minute=5),
    },
    "booking-reminders": {
        "task": "apps.courts.tasks.send_booking_reminders",
        "schedule": crontab(minute=0),
    },
    "expire-pending-partners": {
        "task": "apps.tournaments.tasks.expire_pending_partners",
        "schedule": crontab(minute=0),
    },
}
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "tennisclub"),
        "USER": os.getenv("DB_USER", "tennisclub"),
        "PASSWORD": os.getenv("DB_PASSWORD", "tennisclub"),
        "HOST": os.getenv("DB_HOST", "db"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# Cloudflare Tunnel & Proxy Settings
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Email Configuration
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.example.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() in ("true", "1")
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@tennisclub.local")

# Redis Cache in Production
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://redis:6379/1"),
    }
}
