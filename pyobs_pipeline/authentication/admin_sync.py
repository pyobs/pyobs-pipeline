"""Settings-configured admin account: ADMIN_USERNAME/ADMIN_PASSWORD_HASH, synced to a real
superuser after every `manage.py migrate` (post_migrate signal, wired up in
AuthenticationConfig.ready()), so it authenticates via django.contrib.auth the same way a
Keycloak-linked user does, not just via the session["authenticated"] flag. Mirrors
pyobs-web-admin's pyobs_web_admin/authentication/admin_sync.py. ADMIN_PASSWORD_HASH is already a
Django-format hash (make_password() output, per settings.py's own instructions) - assigned
straight to User.password rather than re-hashed.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import User


def sync_admin_user(sender, **kwargs):
    username = getattr(settings, "ADMIN_USERNAME", "")
    password_hash = getattr(settings, "ADMIN_PASSWORD_HASH", "")
    if not username or not password_hash:
        return

    User.objects.update_or_create(
        username=username,
        defaults={
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
            "password": password_hash,
        },
    )
