import asyncio
import logging
import threading
import time
import traceback

from celery import shared_task
from django.utils import timezone as dj_timezone

from pyobs.object import create_object
from pyobs.utils.pipeline import MasterCalibCreated, ProgressEvent, ScienceFrameProcessed
from reduction.models import ReductionPeriod

log = logging.getLogger(__name__)


def _archive_config(io_type: str, io_config: dict) -> dict:
    if io_type == "local":
        # NOTE: LocalArchive/PyobsArchive set __module__ = "pyobs.utils.archive" for
        # display purposes, but that path isn't actually importable (no such module
        # exists in pyobs-core) -- get_class_from_string needs the real one.
        return {"class": "pyobs.robotic.utils.archive.LocalArchive", "root": io_config.get("path", "")}
    return io_config


def _output_config(io_type: str, io_config: dict) -> str | dict:
    if io_type == "local":
        return io_config.get("path", "")
    return io_config


def build_reduction_config(period: ReductionPeriod) -> dict:
    """Nested pyobs.object config for the Reduction that processes `period`. See the
    "Celery task" section in specs/plans/pyobs-pipeline.md (pyobs-core repo)."""
    assignment = period.site.pipeline_assignment
    pipeline = assignment.pipeline
    steps = [{"class": step.step_class, **step.config} for step in pipeline.steps.all()]
    return {
        "class": "pyobs.utils.pipeline.Reduction",
        **pipeline.period_config,
        "archive": _archive_config(assignment.input_type, assignment.input_config),
        "output": _output_config(assignment.output_type, assignment.output_config),
        "pipeline": {"class": "pyobs.utils.pipeline.Pipeline", "steps": steps},
    }


class _Flusher:
    """Throttled, single-background-thread DB flush shared by _LogCollector and
    _ProgressCollector, both of which write to fields on the same ReductionPeriod row.

    A direct ORM write from inside asyncio.run()'s active event loop raises
    SynchronousOnlyOperation (confirmed empirically) -- Django's async-unsafe guard trips
    on any running loop in the current thread, not just genuinely-async callers -- so the
    write runs on a plain background thread instead, which has no event loop of its own.

    Deliberately ONE shared thread/timer for both fields rather than one each: two
    independent flush threads racing to .update() the same SQLite row concurrently can
    hit "database table is locked" (confirmed by test failure when this was tried) even
    with WAL mode, since each still needs a brief exclusive write lock.
    """

    FLUSH_INTERVAL = 2.0  # seconds, matches period_detail.html's poll interval

    def __init__(self, period_id: int, get_fields) -> None:
        self._period_id = period_id
        self._get_fields = get_fields  # callable() -> dict of ReductionPeriod fields to write
        self._last_flush = 0.0
        self._flush_thread: threading.Thread | None = None

    def _write(self, fields: dict) -> None:
        ReductionPeriod.objects.filter(pk=self._period_id).update(**fields)

    def flush(self) -> None:
        # Skip this round if the previous flush is still in flight, rather than piling
        # up threads -- the next throttled call will pick up everything anyway.
        if self._flush_thread is not None and self._flush_thread.is_alive():
            return
        self._flush_thread = threading.Thread(target=self._write, args=(self._get_fields(),), daemon=True)
        self._flush_thread.start()

    def maybe_flush(self) -> None:
        now = time.monotonic()
        if now - self._last_flush >= self.FLUSH_INTERVAL:
            self.flush()
            self._last_flush = now

    def join(self, timeout: float = 5) -> None:
        if self._flush_thread is not None:
            self._flush_thread.join(timeout=timeout)


class _LogCollector(logging.Handler):
    """Relies on --pool=prefork: each task runs in its own worker process, so a
    process-global root handler only ever sees this task's log records.

    Accumulates log lines in memory; a shared _Flusher (see above) periodically writes
    full_text to the DB while the task runs -- not just once at the end, otherwise the
    "live" log viewer has nothing to show until the task is already done."""

    def __init__(self, prior_logs: str, flusher: "_Flusher") -> None:
        super().__init__()
        self._prior_logs = prior_logs
        self._flusher = flusher
        self.lines: list[str] = []

    @property
    def full_text(self) -> str:
        new_lines = "\n".join(self.lines)
        return f"{self._prior_logs}\n{new_lines}" if self._prior_logs else new_lines

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))
        self._flusher.maybe_flush()


class _ProgressCollector:
    """Accumulates structured progress events from Reduction (master calibs created,
    science frames processed); flushed to the DB via the same shared _Flusher as
    _LogCollector's logs (see _Flusher's docstring for why they share one flush thread).

    Starts empty every run, unlike _LogCollector's logs (which carry prior_logs forward)
    -- a restart is a fresh ReductionPeriod row, so there's no prior progress to append to.
    """

    def __init__(self, flusher: "_Flusher") -> None:
        self._flusher = flusher
        self.calibs: list[dict] = []
        self.frames: dict = {"total": 0, "items": []}

    @property
    def data(self) -> dict:
        return {"calibs": self.calibs, "frames": self.frames}

    def on_progress(self, event: ProgressEvent) -> None:
        if isinstance(event, MasterCalibCreated):
            self.calibs.append(
                {
                    "image_type": event.image_type.value,
                    "instrument": event.instrument,
                    "binning": event.binning,
                    "filter": event.filter_name,
                    "filename": event.filename,
                    "exptime": event.exptime,
                }
            )
        elif isinstance(event, ScienceFrameProcessed):
            self.frames["total"] = event.total
            self.frames["items"].append(
                {"index": event.index, "filename": event.filename, "status": event.status, "error": event.error}
            )

        self._flusher.maybe_flush()


@shared_task(bind=True)
def reduce_period(self, site_id: int, period_id: int) -> None:
    period = ReductionPeriod.objects.select_related("site").get(pk=period_id)
    period.status = "RUNNING"
    period.started_at = dj_timezone.now()
    period.task_id = self.request.id or ""
    period.save(update_fields=["status", "started_at", "task_id"])

    # get_fields() reads handler/progress by name at call time (flush always happens after
    # both are assigned below), so the forward reference here is fine despite the
    # definition order.
    def get_fields() -> dict:
        return {"logs": handler.full_text, "progress": progress.data}

    flusher = _Flusher(period.pk, get_fields)
    handler = _LogCollector(period.logs, flusher)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    progress = _ProgressCollector(flusher)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    try:
        config = build_reduction_config(period)
        reduction = create_object(config, progress_callback=progress.on_progress)
        # siteid is the archive's own site code (e.g. "monets"), which isn't always the
        # same as the display name used in URLs/UI -- falls back to name if unset.
        asyncio.run(reduction(period.site.siteid or period.site.name, period.date.isoformat()))
        period.status = "COMPLETED"
    except Exception:
        period.status = "FAILED"
        handler.lines.append(traceback.format_exc())
    finally:
        root_logger.removeHandler(handler)
        # Wait for any in-flight background flush before writing the final state --
        # otherwise it could complete after this save and clobber it back to stale,
        # incomplete logs/progress.
        flusher.join(timeout=5)
        period.logs = handler.full_text
        period.progress = progress.data
        period.finished_at = dj_timezone.now()
        period.save(update_fields=["status", "logs", "progress", "finished_at"])
