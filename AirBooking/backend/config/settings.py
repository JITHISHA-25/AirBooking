import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def enabled(name, default="false"):
    return os.getenv(name, default).lower() in {"true", "1", "yes"}


def items(name, default):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DEBUG = enabled("DJANGO_DEBUG", "true")
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or (
    "django-insecure-local-airbooking-development-key" if DEBUG else ""
)
if not SECRET_KEY:
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY when DJANGO_DEBUG is false.")

ALLOWED_HOSTS = items("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CORS_ALLOWED_ORIGINS = items("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "booking",
]
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
AUTH_USER_MODEL = "booking.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "Asia/Kolkata"

if os.getenv("POSTGRES_DB"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.getenv("POSTGRES_USER", "airbooking"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }}
else:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 15, "transaction_mode": "IMMEDIATE"},
    }}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["booking.auth.ApprovedJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_RATES": {"register": "20/hour", "login": "30/minute"},
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}
CELERY_TASK_ALWAYS_EAGER = enabled("CELERY_TASK_ALWAYS_EAGER", "true")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_BROKER_CONNECTION_TIMEOUT = 3
CELERY_BROKER_TRANSPORT_OPTIONS = {"max_retries": 0, "socket_connect_timeout": 3}
CELERY_TASK_IGNORE_RESULT = True
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "AirBooking <noreply@example.com>")
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = enabled("EMAIL_USE_TLS", "true")
EMAIL_TIMEOUT = 10
AIRLABS_API_KEY = os.getenv("AIRLABS_API_KEY", "").strip()
FOOD_ORDER_CUTOFF_HOURS = int(os.getenv("FOOD_ORDER_CUTOFF_HOURS", "2"))
if FOOD_ORDER_CUTOFF_HOURS < 0:
    raise ImproperlyConfigured("FOOD_ORDER_CUTOFF_HOURS must be a non-negative integer.")
