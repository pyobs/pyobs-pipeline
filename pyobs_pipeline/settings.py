import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-y*5=%i%$(#iy+p8tmpq)ao0hby$7huewxp2^^zmpvb1y1*nbc!"

DEBUG = True

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "reduction",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "reduction.middleware.LoginRequiredMiddleware",
]

ROOT_URLCONF = "pyobs_pipeline.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "reduction.context_processors.pipeline_version",
                "reduction.context_processors.pyobs_logo",
            ],
        },
    },
]

WSGI_APPLICATION = "pyobs_pipeline.wsgi.application"

# db.sqlite3 lives under ./data/ so it can be mounted as a single volume shared
# by the web, worker, and beat containers (see docker-compose.yml). WAL mode +
# a busy timeout are needed because those three processes open the same file
# concurrently.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "data" / "db.sqlite3",
        "OPTIONS": {
            "init_command": "PRAGMA journal_mode=WAL;",
            "timeout": 20,
        },
    }
}

# Sessions stored in signed cookies — no session table needed
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Single-user credentials — set ADMIN_PASSWORD_HASH in local_settings.py:
#   uv run python -c "from django.contrib.auth.hashers import make_password; print(make_password('yourpassword'))"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = ""

# Celery / Redis
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 86400}

# Beat backfill cap — see reduction/scheduler.py. A site left disabled for a long
# stretch shouldn't dispatch a huge backlog the moment it's re-enabled.
MAX_BACKFILL_DAYS = 7

# Docker Compose (see docker-compose.yml) has no local_settings.py in the image -- these
# env vars are its only config surface, and take priority over the defaults above. A
# bare-metal deploy using local_settings.py instead (below) still wins over both, since
# these env vars are normally unset there.
SECRET_KEY = os.environ.get("SECRET_KEY", SECRET_KEY)
DEBUG = os.environ.get("DEBUG", str(DEBUG)).lower() == "true"
if os.environ.get("ALLOWED_HOSTS"):
    ALLOWED_HOSTS = os.environ["ALLOWED_HOSTS"].split(",")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", ADMIN_USERNAME)
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", ADMIN_PASSWORD_HASH)
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", CELERY_BROKER_URL)
MAX_BACKFILL_DAYS = int(os.environ.get("MAX_BACKFILL_DAYS", MAX_BACKFILL_DAYS))

try:
    from pyobs_pipeline.local_settings import *  # noqa: F401,F403
except ImportError:
    pass
