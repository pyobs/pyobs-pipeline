# pyobs-pipeline

Web-based monitoring and configuration for pyobs data reduction pipelines: monitor
status, view logs, retrigger reduction periods, and configure pipeline steps through a
guided builder, replacing SSH + manual YAML editing. See
[`specs/plans/pyobs-pipeline.md`](https://github.com/pyobs/pyobs-core/blob/develop/specs/plans/pyobs-pipeline.md)
in pyobs-core for the full design.

## Deployment (Docker Compose)

Four services in one `docker-compose.yml`, all on one host: `web` (gunicorn), `worker`
(Celery), `beat` (Celery Beat with the DB-backed `DbScheduler`), and `redis` (broker).

### Initial setup

```sh
git clone <this repo> pyobs-pipeline && cd pyobs-pipeline
cp .env.example .env
mkdir -p data
```

Fill in `.env`:

```sh
# SECRET_KEY
uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# ADMIN_PASSWORD_HASH
DJANGO_SETTINGS_MODULE=pyobs_pipeline.settings uv run python -c \
  "from django.contrib.auth.hashers import make_password; print(make_password('yourpassword'))"
```

`ALLOWED_HOSTS` is the hostname/IP the app is reached at. `CELERY_BROKER_URL` should stay
`redis://redis:6379/0` (the Compose service name, not `localhost`) unless Redis is hosted
elsewhere.

**`ADMIN_PASSWORD_HASH` contains `$` characters** (`pbkdf2_sha256$...$...$...`) — docker
compose interpolates `.env` file values, so a bare `$` there is read as a variable reference
and silently blanked. With a real hash that wipes out the salt and hash segments (they look
like valid variable names), leaving a truncated hash that makes every login fail with a 500.
Double every `$` to `$$` when pasting the hash in; Compose unescapes `$$` back to a single `$`
inside the container. `.env.example` shows the escaped form. (The legacy `docker-compose` v1
instead passes `.env` values through verbatim — there, use the hash exactly as
`make_password()` generated it, with no escaping.)

Verify the hash arrived intact after `up`, before relying on login:

```sh
docker compose exec web printenv ADMIN_PASSWORD_HASH
# pbkdf2_sha256$1500000$...   <- single "$" signs, no "$$" anywhere
```

Bring everything up and run migrations once:

```sh
docker compose up -d --build
docker compose exec web uv run python manage.py migrate
```

The app is now at `http://<host>:8000/`, log in with the `ADMIN_USERNAME`/password from
`.env`.

### Operating

```sh
docker compose logs -f web      # or worker / beat / redis
docker compose ps
```

`db.sqlite3` lives at `./data/db.sqlite3`, shared by all three app containers via WAL
mode (see `pyobs_pipeline/settings.py`). It's a single file — back it up with a periodic
`cp`/`rsync`, no separate DB service to manage. Redis's own volume (`redis-data`) only
holds in-flight task state, not anything that needs backing up.

`--pool=prefork` on the `worker` service matters: it's what makes the Stop action's
`revoke(terminate=True)` (see `reduction/period_actions.py`) actually kill a running task
rather than just marking it revoked.

### Updating

```sh
git pull
docker compose up -d --build
docker compose exec web uv run python manage.py migrate
```

## Local development

```sh
uv sync
cp pyobs_pipeline/local_settings.py.example pyobs_pipeline/local_settings.py
# fill in ADMIN_USERNAME / ADMIN_PASSWORD_HASH
uv run python manage.py migrate
uv run python manage.py runserver
```

Celery worker/beat locally (needs a local Redis):

```sh
uv run celery -A pyobs_pipeline worker --loglevel=info --pool=prefork
uv run celery -A pyobs_pipeline beat --loglevel=info --scheduler reduction.scheduler.DbScheduler
```
