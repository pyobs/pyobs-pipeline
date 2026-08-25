Configuration
#############

Controlled by environment variables (``.env``, passed straight through to the web/worker/beat
containers by ``docker-compose.yml`` — see ``pyobs_pipeline/settings.py`` for how they're read).

``SECRET_KEY`` (no default — required)
    Django secret key. See :doc:`installation` for how to generate one.

``DEBUG`` (default: ``false``)
    Set to ``true`` for development.

``ALLOWED_HOSTS`` (no default — required)
    The hostname/IP the app is reached at.

``ADMIN_USERNAME`` (default: ``admin``), ``ADMIN_PASSWORD_HASH`` (no default — required)
    The single admin account this app is logged into with. See :doc:`installation` for how to
    generate the hash, and the ``$``-escaping gotcha under Docker Compose specifically.

``CELERY_BROKER_URL`` (default: ``redis://redis:6379/0``)
    Redis connection for Celery. ``redis`` is the Compose service name, not ``localhost`` —
    containers reach each other by service name on the default Compose network.

``MAX_BACKFILL_DAYS`` (default: ``7``)
    How many past days a newly enabled site/pipeline assignment backfills reduction periods for.

``CSRF_TRUSTED_ORIGINS`` (no default)
    Comma-separated list of full origins (scheme included) the app is really served behind.
    **Required** behind any TLS-terminating reverse proxy — see :doc:`installation`.

``TRUST_X_FORWARDED_PROTO`` (default: ``false``)
    Set to ``true`` when the reverse proxy also sets the ``X-Forwarded-Proto`` header, so Django
    treats requests as HTTPS (``request.is_secure()`` is ``True``). Not required for login once
    ``CSRF_TRUSTED_ORIGINS`` is set, but keeps scheme-dependent behavior correct. Make sure the
    proxy actually overwrites this header — never trust whatever the client sends.

Beyond the environment, sites, pipelines, and pipeline steps are configured through the web UI
itself (or the Django admin) — see :doc:`architecture` for the domain model.
