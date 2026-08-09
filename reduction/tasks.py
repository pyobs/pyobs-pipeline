import asyncio
import logging
import traceback

from celery import shared_task
from django.utils import timezone as dj_timezone

from pyobs.object import create_object
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


class _LogCollector(logging.Handler):
    """Relies on --pool=prefork: each task runs in its own worker process, so a
    process-global root handler only ever sees this task's log records."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@shared_task(bind=True)
def reduce_period(self, site_id: int, period_id: int) -> None:
    period = ReductionPeriod.objects.select_related("site").get(pk=period_id)
    period.status = "RUNNING"
    period.started_at = dj_timezone.now()
    period.task_id = self.request.id or ""
    period.save(update_fields=["status", "started_at", "task_id"])

    handler = _LogCollector()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    try:
        config = build_reduction_config(period)
        reduction = create_object(config)
        asyncio.run(reduction(period.site.name, period.date.isoformat()))
        period.status = "COMPLETED"
    except Exception:
        period.status = "FAILED"
        handler.lines.append(traceback.format_exc())
    finally:
        root_logger.removeHandler(handler)
        new_lines = "\n".join(handler.lines)
        period.logs = f"{period.logs}\n{new_lines}" if period.logs else new_lines
        period.finished_at = dj_timezone.now()
        period.save(update_fields=["status", "logs", "finished_at"])
