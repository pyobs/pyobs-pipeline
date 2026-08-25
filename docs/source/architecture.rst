Architecture
############

*pyobs-pipeline* is a stand-alone Django + Celery service — no fleet-module dependency, though
pipeline steps are typically ``pyobs.images.processors.*`` classes and I/O can point at a
`pyobs-archive <https://github.com/pyobs/pyobs-archive>`_ instance (below).

Domain model
************

- **Site** — an observing site (lat/lon/timezone) with a trigger rule for when its reduction
  period should run each day: ``sunrise``/``sunset`` + an hour offset, or a fixed local time.
- **Pipeline** — a named, reusable sequence of **PipelineStep** rows (an ordered dotted-path
  ``step_class``, e.g. ``pyobs.images.processors.misc.Calibration``, plus its JSON config), and
  top-level ``period_config`` (kwargs for the reduction object itself: ``min_flats``,
  ``filenames_calib``, ``create_calibs``, ``calib_science``).
- **SitePipeline** — assigns one Pipeline to one Site (one-to-one), with an input and output I/O
  config each: either a local directory (``{"path": "/data/raw"}``) or a pyobs-archive connection
  (``{"class": "pyobs.robotic.utils.archive.PyobsArchive", "url": "...", "token": "..."}``) — a
  site can read raw frames from one and write reduced frames to the other.
- **ReductionPeriod** — one day's reduction run for a site: ``PENDING`` (row created by the
  trigger event, not yet dispatched) → ``QUEUED`` → ``RUNNING`` → ``COMPLETED``/``FAILED``, or
  ``CANCELLED`` (manually stopped or reset). Carries ``logs`` (plain text, polled live — see
  below) and ``progress`` (JSON: per-calib and per-frame status).

Scheduling and execution
***************************

Celery Beat, using the DB-backed ``reduction.scheduler.DbScheduler`` (not the static
crontab-in-settings scheduler Celery ships with), evaluates each enabled Site's trigger rule and
creates a ``PENDING`` ``ReductionPeriod`` when it fires. The Celery **worker** then picks it up
and runs the assigned Pipeline's steps in order against the input I/O, writing to the output I/O.

Stopping a running period (``period_stop``) calls ``revoke(terminate=True)`` on its Celery task —
this only actually kills the process because the worker service runs with ``--pool=prefork``
(see :doc:`installation`); other pool types can't terminate a running task, only mark it revoked.

The one JSON endpoint, ``/periods/<pk>/api/status/``, is polled by the period detail page's log
viewer while a period is ``QUEUED``/``RUNNING`` — logs live only in the DB
(``ReductionPeriod.logs``), there's no file to tail. It returns ``status``, ``status_display``,
``logs``, ``progress``, ``started_at``, ``finished_at``.
