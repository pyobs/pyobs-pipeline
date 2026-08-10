# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A standalone Django app for monitoring and configuring pyobs data reduction pipelines: site
scheduling, a pipeline builder (dynamically introspects pyobs-core processor classes), reduction
period tracking with manual start/stop/reset/restart, a live log viewer, and a dashboard. Replaces
SSH + manual YAML editing for operating the pipeline. Full design/rationale in
`specs/plans/pyobs-pipeline.md` in the `pyobs-core` repo (sibling checkout, or
https://github.com/pyobs/pyobs-core/blob/develop/specs/plans/pyobs-pipeline.md).

Single Django app named `reduction` inside the project `pyobs_pipeline`.

## Commands

```sh
uv sync                                              # install deps
uv run python manage.py migrate                      # apply migrations
uv run python manage.py runserver                     # dev server
uv run python manage.py test reduction                 # full test suite
uv run python manage.py test reduction.tests.test_views # one test module
uv run python manage.py test reduction.tests.test_views.PeriodViewTests.test_start_on_enabled_site  # one test

uv run celery -A pyobs_pipeline worker --loglevel=info --pool=prefork   # needs local Redis
uv run celery -A pyobs_pipeline beat --loglevel=info --scheduler reduction.scheduler.DbScheduler
```

Tests use Django's isolated in-memory test database — never touch `data/db.sqlite3`, the real
dev database. No separate lint/format tooling is configured in this repo.

Local dev needs `pyobs_pipeline/local_settings.py` (gitignored; copy
`pyobs_pipeline/local_settings.py.example`) for `ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH` at minimum.
Docker Compose deployment instead reads all config from env vars (`.env`) — see README.md for the
full setup/operate/update flow, including a real gotcha: `ADMIN_PASSWORD_HASH` contains literal
`$` characters that Compose will silently blank out in `.env` unless escaped to `$$`.

## Architecture

**Models** (`reduction/models.py`): `Site` (location + trigger schedule) → `SitePipeline`
(one-to-one, assigns a `Pipeline` to a `Site`, plus input/output archive config) → `Pipeline` →
`PipelineStep` (ordered, `step_class` dotted path + JSON `config`). `ReductionPeriod` is one row
per site per reduction run, with a `status` state machine (`PENDING` → `QUEUED` → `RUNNING` →
`COMPLETED`/`FAILED`/`CANCELLED`).

**Design constraint that shapes a lot of the code**: `ReductionPeriod` rows are *only* ever created
by the Beat trigger event or by Restart (which copies site+date from an existing row) — there is
deliberately no "create a period for an arbitrary date" UI or management command. `Site.enabled`
gates automatic *dispatch* only, not row creation: a disabled site still gets `PENDING` rows every
trigger tick, just never auto-queued, for manual-only operation.

**Pipeline builder** (`reduction/step_fields.py`): `discover_step_templates()` walks
`pyobs.images.processors` at runtime via `pkgutil`, collecting every concrete (non-abstract)
`ImageProcessor` subclass — no static registry, so it stays in sync with pyobs-core automatically.
`get_step_fields()` introspects a processor class's `__init__` via `inspect.signature(...,
eval_str=True)` (needed because pyobs-core uses `from __future__ import annotations` everywhere) to
generate form fields, merging in `ImageProcessor`'s own base params (e.g. `on_error`) since most
processors only inherit them through `**kwargs` rather than redeclaring them. The `archive` param
is hidden here — see below.

**Celery task** (`reduction/tasks.py`): `build_reduction_config()` assembles a nested
`pyobs.object`-style config dict from a `ReductionPeriod`'s site/pipeline/steps, then
`reduce_period` runs it via `create_object()` + `asyncio.run()`. A step's `archive` key is
deliberately never written into its config — pyobs-core's `PipelineMixin` (as of the pinned
pyobs-core rev) auto-fills a step's `archive` from the pipeline's own archive when the step doesn't
specify one, so `Calibration` steps don't need to repeat the site's already-configured archive.

**Manual controls** (`reduction/period_actions.py`): `start_period`/`stop_period`/`reset_period`/
`restart_period` enforce the legal status transitions (e.g. Stop only valid while `RUNNING`, and
calls `AsyncResult(task_id).revoke(terminate=True)` — requires the worker's `--pool=prefork`) and
the one-active-run-per-site-date invariant.

**Scheduler** (`reduction/scheduler.py`, `reduction/turnover.py`): `DbScheduler` is a custom
`celery.beat.Scheduler` that reads `Site` rows from the DB every tick instead of a static
`beat_schedule` dict. `get_next_turnover`/`get_period_label`/`get_missing_period_dates` compute,
per `Site.trigger_type` (sunrise/sunset/fixed_time), when Beat should fire versus which calendar
date a period belongs to — these are deliberately separate concepts (a frame taken after midnight
belongs to the previous evening's date). Backfill walks forward through actual trigger instants
rather than comparing calendar-date labels directly, because a label only changes at the *opposite*
reference crossing (e.g. sunset for a sunrise-triggered site), not at the trigger instant itself —
comparing labels alone would miss a same-day trigger for several hours after it fires.

**pyobs-core dependency**: pinned to a git commit (`[tool.uv.sources]` in `pyproject.toml`), not
PyPI, since features this app depends on (the `Night`→`Reduction` rename, archive auto-propagation)
haven't shipped in a pyobs-core release yet. Bump the pinned `rev` when picking up a relevant
upstream fix. For local tandem development against an in-progress pyobs-core change, temporarily
point the source at `{ path = "../pyobs-core", editable = true }` instead of the git pin — don't
commit that swap.
