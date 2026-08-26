# pyobs-pipeline

Web-based monitoring and configuration for pyobs data reduction pipelines: monitor
status, view logs, retrigger reduction periods, and configure pipeline steps through a
guided builder, replacing SSH + manual YAML editing.

![Dashboard showing site cards with last period, next trigger, and input/output status, plus a table of recent reduction periods](docs/source/_static/screenshots/dashboard.jpg)

## Documentation

Full installation (Docker Compose, including the `.env` `$`-escaping gotcha and reverse-proxy
CSRF setup), configuration (every environment variable), architecture (the Site/Pipeline/Period
domain model and how Celery Beat schedules a run), and local development: see
[`docs/source/`](docs/source/) (built with Sphinx — `cd docs && uv run --group dev make html`).

## Development

```bash
git clone https://github.com/pyobs/pyobs-pipeline.git
cd pyobs-pipeline
uv sync
```

See [`docs/source/development.rst`](docs/source/development.rst) for the full local-dev flow
(including running Celery worker/beat locally), and
[`docs/source/installation.rst`](docs/source/installation.rst) for the Docker Compose production
setup.
