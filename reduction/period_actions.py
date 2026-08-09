"""Manual start/stop/reset/restart actions on a ReductionPeriod. See "Manual control"
in specs/plans/pyobs-pipeline.md (pyobs-core repo).
"""

from celery.result import AsyncResult
from django.utils import timezone as dj_timezone

from reduction.models import ReductionPeriod
from reduction.tasks import reduce_period


class PeriodActionError(Exception):
    """Raised when an action isn't valid for the period's current state."""


def _append_log(period: ReductionPeriod, line: str) -> None:
    period.logs = f"{period.logs}\n{line}" if period.logs else line


def _has_active_conflict(period: ReductionPeriod) -> bool:
    """Another QUEUED/RUNNING row already exists for this site+date -- see "Two rows for
    the same site+date can't both be dispatchable at once" in the plan."""
    return (
        ReductionPeriod.objects.filter(site=period.site, date=period.date, status__in=("QUEUED", "RUNNING"))
        .exclude(pk=period.pk)
        .exists()
    )


def start_period(period: ReductionPeriod) -> None:
    if period.status not in ("PENDING", "FAILED", "CANCELLED"):
        raise PeriodActionError(f"Cannot start a period in status {period.status}.")
    if _has_active_conflict(period):
        raise PeriodActionError("Another run for this site/date is already queued or running.")

    period.status = "QUEUED"
    period.save(update_fields=["status"])
    result = reduce_period.delay(period.site_id, period.pk)
    period.task_id = result.id
    period.save(update_fields=["task_id"])


def stop_period(period: ReductionPeriod) -> None:
    if period.status != "RUNNING":
        raise PeriodActionError("Can only stop a running period.")
    if period.task_id:
        AsyncResult(period.task_id).revoke(terminate=True)
    period.status = "CANCELLED"
    _append_log(period, "[manual] Cancelled by operator (stop).")
    period.finished_at = dj_timezone.now()
    period.save(update_fields=["status", "logs", "finished_at"])


def reset_period(period: ReductionPeriod) -> None:
    """Escape hatch for a period stuck in QUEUED/RUNNING whose task_id is no longer
    live (worker crashed/restarted without revoking cleanly) -- no revoke attempted."""
    if period.status not in ("QUEUED", "RUNNING"):
        raise PeriodActionError("Can only reset a queued or running period.")
    period.status = "CANCELLED"
    _append_log(period, "[manual] Reset by operator (orphaned task, no revoke attempted).")
    period.finished_at = dj_timezone.now()
    period.save(update_fields=["status", "logs", "finished_at"])


def restart_period(period: ReductionPeriod) -> ReductionPeriod:
    """Stop (if RUNNING) or reset (if QUEUED) the current row, then start a fresh row
    for the same site+date. The old row is kept for its log history."""
    if period.status == "RUNNING":
        stop_period(period)
    elif period.status == "QUEUED":
        reset_period(period)

    new_period = ReductionPeriod.objects.create(site=period.site, date=period.date, status="PENDING")
    start_period(new_period)
    return new_period
