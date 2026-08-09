"""Celery Beat scheduler that reads Site rows from the DB on every tick, instead of a
static beat_schedule dict fixed at process start. See "Beat schedule" in
specs/plans/pyobs-pipeline.md (pyobs-core repo).

Run with: celery -A pyobs_pipeline beat --scheduler reduction.scheduler.DbScheduler
"""

from __future__ import annotations

import logging

from celery.beat import Scheduler
from django.conf import settings

from reduction.models import ReductionPeriod, Site
from reduction.tasks import reduce_period
from reduction.turnover import get_missing_period_dates

log = logging.getLogger(__name__)


class DbScheduler(Scheduler):
    # How often tick() re-checks the DB for due sites. Independent of any per-site
    # trigger time -- just how promptly a trigger is noticed after it occurs.
    max_interval = 60

    def tick(self, *args, **kwargs):
        for site in Site.objects.all():
            self._create_pending_periods(site)
        return super().tick(*args, **kwargs)

    def _create_pending_periods(self, site: Site) -> None:
        last_period = ReductionPeriod.objects.filter(site=site).order_by("-date").first()
        since = last_period.date if last_period else None

        for date in get_missing_period_dates(site, since=since, max_days=settings.MAX_BACKFILL_DAYS):
            period, created = ReductionPeriod.objects.get_or_create(
                site=site, date=date, defaults={"status": "PENDING"}
            )
            if not created:
                continue
            if site.enabled:
                period.status = "QUEUED"
                period.save(update_fields=["status"])
                reduce_period.delay(site.id, period.id)
