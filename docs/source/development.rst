Development
###########

::

    git clone https://github.com/pyobs/pyobs-pipeline.git
    cd pyobs-pipeline
    uv sync
    cp pyobs_pipeline/local_settings.py.example pyobs_pipeline/local_settings.py
    # fill in ADMIN_USERNAME / ADMIN_PASSWORD_HASH
    uv run python manage.py migrate
    uv run python manage.py runserver

Celery worker/beat locally (needs a local Redis)::

    uv run celery -A pyobs_pipeline worker --loglevel=info --pool=prefork
    uv run celery -A pyobs_pipeline beat --loglevel=info --scheduler reduction.scheduler.DbScheduler

Tests::

    uv run python manage.py test
