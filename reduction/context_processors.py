import tomllib

from django.conf import settings
from django.templatetags.static import static

# Cached for the life of the process: this app runs straight from source via uv, no
# installed distribution to read an importlib.metadata entry from -- pyproject.toml
# itself is the only source of truth, and it can't change without a redeploy that
# restarts the process anyway. Mirrors pyobs-web-admin's modules/context_processors.py.
_pipeline_version_cache: str | None = None


def _pipeline_version() -> str | None:
    global _pipeline_version_cache
    if _pipeline_version_cache is None:
        try:
            data = tomllib.loads((settings.BASE_DIR / "pyproject.toml").read_text())
            _pipeline_version_cache = data.get("project", {}).get("version", "") or ""
        except OSError:
            _pipeline_version_cache = ""
    return _pipeline_version_cache or None


def pipeline_version(request):
    return {"pipeline_version": _pipeline_version()}


def keycloak_login(request):
    # keycloak_login_enabled gates the login page's Keycloak button(s) - SERVER_URL unset means
    # Keycloak is disabled entirely (see PYOBS_AUTH in settings.py). The template additionally
    # gates the one-click-IdP button on keycloak_idp_hint, so a hint without SERVER_URL degrades
    # to no buttons rather than a dead link. Mirrors pyobs-web-admin's
    # modules/context_processors.py.
    pyobs_auth_settings = getattr(settings, "PYOBS_AUTH", {})
    return {
        "keycloak_login_enabled": bool(pyobs_auth_settings.get("SERVER_URL")),
        "keycloak_idp_hint": pyobs_auth_settings.get("IDP_HINT", ""),
        "keycloak_idp_label": pyobs_auth_settings.get("IDP_LABEL", ""),
    }


def pyobs_logo(request):
    # Deployments can point these at their own logo via settings/env; default to the
    # bundled pyobs logo (reduction/static/img/pyobs-logo-{light,dark}.gif). Two
    # variants because the wordmark's "py" is black - invisible on a dark sidebar
    # without a light-on-dark version to swap in.
    return {
        "pyobs_logo_light_url": getattr(settings, "PYOBS_LOGO_LIGHT_URL", None) or static("img/pyobs-logo-light.gif"),
        "pyobs_logo_dark_url": getattr(settings, "PYOBS_LOGO_DARK_URL", None) or static("img/pyobs-logo-dark.gif"),
    }
