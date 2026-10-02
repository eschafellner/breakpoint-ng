import os
from .base import *

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Database configuration: support SQLite for development/testing, PostgreSQL if configured
DATABASES = {
    "default": {
        "ENGINE": os.getenv("DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.getenv("DB_NAME", BASE_DIR / "db.sqlite3"),
    }
}

if os.getenv("DB_ENGINE") == "django.db.backends.postgresql":
    DATABASES["default"].update({
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", "postgres"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    })

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Test / Dev cache
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}
