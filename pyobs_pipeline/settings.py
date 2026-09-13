import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-y*5=%i%$(#iy+p8tmpq)ao0hby$7huewxp2^^zmpvb1y1*nbc!"

DEBUG = True

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "pyobs_auth",
    "pyobs_pipeline.authentication",
    "reduction",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # after AuthenticationMiddleware (needs request.user) - re-checks a Keycloak-backed session's
    # authorization once its access token expires, instead of only at next login. See pyobs-auth's
    # docs/source/configuration.rst and pyobs-core's specs/design/shared-authz-keycloak.md.
    "pyobs_auth.middleware.KeycloakSessionRefreshMiddleware",
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
                "django.contrib.auth.context_processors.auth",
                "reduction.context_processors.pipeline_version",
                "reduction.context_processors.pyobs_logo",
                "reduction.context_processors.keycloak_login",
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

# DB-backed sessions (same sqlite file/WAL setup as above) rather than signed cookies -
# pyobs-auth's Keycloak login stores a refresh token in the session so
# KeycloakSessionRefreshMiddleware can silently re-authorize before the access token expires;
# a cookie-backed session can't hold that (it's readable, if not writable, by the browser) and
# pyobs-auth silently skips storing it there, degrading revocation to "next login only". Matches
# pyobs-web-admin/pyobs-portal, which are both db-backed for the same reason.
SESSION_ENGINE = "django.contrib.sessions.backends.db"

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
# Break-glass fallback once Keycloak (below) is configured — kept working rather than removed,
# since it's the only way in if Keycloak itself is unreachable.
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = ""

# Keycloak login (optional addon on top of the shared admin/password login above, not a
# replacement - leave SERVER_URL unset to disable it entirely; the login page won't show the
# button either). Authorization is the REQUIRED_GROUPS claims gate below (Keycloak group
# membership) - see pyobs-core's specs/design/shared-authz-keycloak.md and this repo's
# specs/plans/2026-09-13-keycloak-login.md.
PYOBS_AUTH = {
    "SERVER_URL": "",
    "REALM": "pyobs",
    "CLIENT_ID": "pipeline",
    "CLIENT_SECRET": "",
    "REDIRECT_URI": "",
    "POST_LOGOUT_REDIRECT_URI": "",
    # Optional one-click IdP login: IDP_HINT is passed to Keycloak as kc_idp_hint (skips its
    # login/IdP-selection page, going straight to that identity provider, e.g. GWDG SSO);
    # IDP_LABEL is the button label on the login page. Both are deployment-specific.
    "IDP_HINT": "",
    "IDP_LABEL": "",
    "USER_RESOLVER": "pyobs_pipeline.authentication.keycloak.resolve_user",
    # Membership in this Keycloak group is what authorizes a user to use pipeline at all - no
    # per-action (start/stop/reset) role on top of it, matching today's behavior where any
    # logged-in user can do everything. Empty disables the gate entirely.
    "REQUIRED_GROUPS": ["/pyobs-pipeline"],
    # No local activation gate to layer on top of REQUIRED_GROUPS - unlike web-admin, pipeline
    # has no Django-admin-backed activation UI, so this stays False (the default).
    "ENFORCE_LOCAL_ACTIVE": False,
}

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
PYOBS_AUTH["SERVER_URL"] = os.environ.get("KEYCLOAK_SERVER_URL", PYOBS_AUTH["SERVER_URL"])
PYOBS_AUTH["CLIENT_ID"] = os.environ.get("KEYCLOAK_CLIENT_ID", PYOBS_AUTH["CLIENT_ID"])
PYOBS_AUTH["CLIENT_SECRET"] = os.environ.get("KEYCLOAK_CLIENT_SECRET", PYOBS_AUTH["CLIENT_SECRET"])
PYOBS_AUTH["REDIRECT_URI"] = os.environ.get("KEYCLOAK_REDIRECT_URI", PYOBS_AUTH["REDIRECT_URI"])
PYOBS_AUTH["POST_LOGOUT_REDIRECT_URI"] = os.environ.get(
    "KEYCLOAK_POST_LOGOUT_REDIRECT_URI", PYOBS_AUTH["POST_LOGOUT_REDIRECT_URI"]
)
PYOBS_AUTH["IDP_HINT"] = os.environ.get("KEYCLOAK_IDP_HINT", PYOBS_AUTH["IDP_HINT"])
PYOBS_AUTH["IDP_LABEL"] = os.environ.get("KEYCLOAK_IDP_LABEL", PYOBS_AUTH["IDP_LABEL"])
if os.environ.get("KEYCLOAK_REQUIRED_GROUPS"):
    PYOBS_AUTH["REQUIRED_GROUPS"] = [
        group.strip() for group in os.environ["KEYCLOAK_REQUIRED_GROUPS"].split(",") if group.strip()
    ]
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", CELERY_BROKER_URL)
MAX_BACKFILL_DAYS = int(os.environ.get("MAX_BACKFILL_DAYS", MAX_BACKFILL_DAYS))

# Served behind a TLS-terminating proxy (nginx/caddy/tunnel), the browser talks
# HTTPS while gunicorn sees plain HTTP, so the CSRF middleware's Origin check
# rejects every POST (login included) with "403 CSRF verification failed" unless
# the browser's real origin is trusted here. Comma-separated full origins, e.g.
# "https://pipeline.monet.uni-goettingen.de". See README.
CSRF_TRUSTED_ORIGINS = []
if os.environ.get("CSRF_TRUSTED_ORIGINS"):
    CSRF_TRUSTED_ORIGINS = [
        origin.strip()
        for origin in os.environ["CSRF_TRUSTED_ORIGINS"].split(",")
        if origin.strip()
    ]

# Optional: set TRUST_X_FORWARDED_PROTO=true when the proxy also sets
# X-Forwarded-Proto, so request.is_secure() reflects HTTPS. Not required for
# login once CSRF_TRUSTED_ORIGINS is set, but keeps scheme-dependent behavior
# (e.g. secure cookies, referer checks for requests without an Origin header)
# correct. The proxy must overwrite X-Forwarded-Proto.
if os.environ.get("TRUST_X_FORWARDED_PROTO", "").lower() == "true":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

try:
    from pyobs_pipeline.local_settings import *  # noqa: F401,F403
except ImportError:
    pass
