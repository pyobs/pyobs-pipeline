Installation
############

Docker Compose is the supported way to run *pyobs-pipeline*. Four services in one
``docker-compose.yml``, all on one host: **web** (gunicorn), **worker** (Celery), **beat**
(Celery Beat with the DB-backed ``DbScheduler``), and **redis** (broker).

Initial setup::

    git clone https://github.com/pyobs/pyobs-pipeline.git
    cd pyobs-pipeline
    cp .env.example .env
    mkdir -p data

Fill in ``.env`` — generate ``SECRET_KEY`` and ``ADMIN_PASSWORD_HASH``::

    uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

    DJANGO_SETTINGS_MODULE=pyobs_pipeline.settings uv run python -c \
      "from django.contrib.auth.hashers import make_password; print(make_password('yourpassword'))"

``ALLOWED_HOSTS`` is the hostname/IP the app is reached at. ``CELERY_BROKER_URL`` should stay
``redis://redis:6379/0`` (the Compose service name, not ``localhost``) unless Redis is hosted
elsewhere. See :doc:`configuration` for every setting.

.. warning::
   **``ADMIN_PASSWORD_HASH`` contains ``$`` characters** (``pbkdf2_sha256$...$...$...``) — Docker
   Compose interpolates ``.env`` file values, so a bare ``$`` there is read as a variable
   reference and silently blanked. With a real hash, that wipes out the salt and hash segments
   (they look like valid variable names), leaving a truncated hash that makes every login fail
   with a 500. Double every ``$`` to ``$$`` when pasting the hash in — Compose unescapes ``$$``
   back to a single ``$`` inside the container. ``.env.example`` shows the escaped form. (The
   legacy ``docker-compose`` v1 instead passes ``.env`` values through verbatim — there, use the
   hash exactly as ``make_password()`` generated it, with no escaping.)

   Verify the hash arrived intact after ``up``, before relying on login::

       docker compose exec web printenv ADMIN_PASSWORD_HASH
       # pbkdf2_sha256$1500000$...   <- single "$" signs, no "$$" anywhere

Bring everything up and run migrations once::

    docker compose up -d --build
    docker compose exec web uv run python manage.py migrate

The app is now at ``http://<host>:8000/``, log in with the ``ADMIN_USERNAME``/password from
``.env``.

Serving over HTTPS (reverse proxy / tunnel)
**********************************************

The Compose **web** service speaks plain HTTP on ``:8000`` (no TLS). If you put a
TLS-terminating proxy in front of it — nginx, caddy, a cloudflared/SSH tunnel — you must tell
Django the origin the browser is really talking to, or **every POST (the login form included)
fails with** ``403 CSRF verification failed. Request aborted``. That's Django's CSRF ``Origin``
check comparing the browser's ``Origin: https://<host>`` header against the scheme gunicorn sees
(``http``).

Set ``CSRF_TRUSTED_ORIGINS`` in ``.env`` (a full origin, scheme included; comma-separate
multiple)::

    # e.g. for https://pipeline.monet.uni-goettingen.de:
    CSRF_TRUSTED_ORIGINS=https://pipeline.monet.uni-goettingen.de

If your proxy sets ``X-Forwarded-Proto`` (nginx's ``proxy_set_header X-Forwarded-Proto $scheme;``,
caddy does by default), also set ``TRUST_X_FORWARDED_PROTO=true`` so ``request.is_secure()``
reflects HTTPS. Make sure the proxy overwrites that header — never trust whatever the client
sends. Then redeploy: ``docker compose up -d --build`` (the web/worker/beat containers all read
the env vars).

Operating
*********

::

    docker compose logs -f web      # or worker / beat / redis
    docker compose ps

``db.sqlite3`` lives at ``./data/db.sqlite3``, shared by all three app containers via WAL mode
(see ``pyobs_pipeline/settings.py``). It's a single file — back it up with a periodic ``cp``/
``rsync``, no separate DB service to manage. Redis's own volume (``redis-data``) only holds
in-flight task state, not anything that needs backing up.

``--pool=prefork`` on the **worker** service matters: it's what makes the Stop action's
``revoke(terminate=True)`` (see ``reduction/period_actions.py``) actually kill a running task
rather than just marking it revoked.

Updating
********

::

    git pull
    docker compose up -d --build
    docker compose exec web uv run python manage.py migrate

See :doc:`development` for running it locally without Docker.
