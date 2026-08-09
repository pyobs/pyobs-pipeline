import datetime as dt
from unittest.mock import patch

from django.test import TestCase, override_settings

from reduction.models import Pipeline, PipelineStep, ReductionPeriod, Site, SitePipeline
from reduction.scheduler import DbScheduler
from reduction.turnover import get_missing_period_dates, get_next_turnover, get_period_label


def _site(**kwargs):
    defaults = dict(name="S1", lat=51.56, lon=9.94, timezone="Europe/Berlin", trigger_type="sunrise", delay_hours=3.0)
    defaults.update(kwargs)
    return Site.objects.create(**defaults)


class TurnoverTests(TestCase):
    """Not saved to the DB -- Site instances built in memory are enough here."""

    def test_sunrise_next_turnover_is_in_the_future(self):
        site = Site(name="t", lat=51.56, lon=9.94, timezone="Europe/Berlin", trigger_type="sunrise", delay_hours=3.0)
        now = dt.datetime(2026, 8, 9, 12, 0, tzinfo=dt.timezone.utc)
        turnover = get_next_turnover(site, now=now)
        self.assertGreater(turnover, now)

    def test_fixed_time_turnover(self):
        site = Site(name="t", lat=51.56, lon=9.94, timezone="Europe/Berlin", trigger_type="fixed_time", trigger_time=dt.time(22, 0))
        now = dt.datetime(2026, 8, 9, 12, 0, tzinfo=dt.timezone.utc)  # 14:00 local
        turnover = get_next_turnover(site, now=now)
        local = turnover.astimezone(dt.timezone(dt.timedelta(hours=2)))
        self.assertEqual(local.date(), dt.date(2026, 8, 9))
        self.assertEqual(local.hour, 22)

    def test_period_label_lags_the_opposite_reference_not_the_trigger(self):
        """A sunrise trigger's label only flips at the following sunset, not at the
        trigger instant itself -- see reduction/turnover.py's docstring for why this
        matters for backfill correctness."""
        site = Site(name="t", lat=51.56, lon=9.94, timezone="Europe/Berlin", trigger_type="sunrise", delay_hours=3.0)
        before_trigger = dt.datetime(2026, 8, 9, 5, 0, tzinfo=dt.timezone.utc)
        after_trigger_same_morning = dt.datetime(2026, 8, 9, 9, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(get_period_label(site, at=before_trigger), get_period_label(site, at=after_trigger_same_morning))

    def test_missing_period_dates_capped_by_max_days(self):
        site = Site(name="t", lat=51.56, lon=9.94, timezone="Europe/Berlin", trigger_type="sunrise", delay_hours=3.0)
        now = dt.datetime(2026, 8, 9, 12, 0, tzinfo=dt.timezone.utc)
        dates = get_missing_period_dates(site, since=None, max_days=3, now=now)
        self.assertLessEqual(len(dates), 4)  # max_days + 1 margin, see turnover.py
        self.assertEqual(dates, sorted(dates))

    def test_missing_period_dates_excludes_up_to_since(self):
        site = Site(name="t", lat=51.56, lon=9.94, timezone="Europe/Berlin", trigger_type="sunrise", delay_hours=3.0)
        now = dt.datetime(2026, 8, 9, 12, 0, tzinfo=dt.timezone.utc)
        dates = get_missing_period_dates(site, since=dt.date(2026, 8, 9), max_days=7, now=now)
        self.assertEqual(dates, [])


class DbSchedulerTests(TestCase):
    def setUp(self):
        self.pipeline = Pipeline.objects.create(name="P1")
        PipelineStep.objects.create(pipeline=self.pipeline, order=0, step_class="pyobs.images.processors.image.Flip")

    def _assign(self, site):
        SitePipeline.objects.create(
            site=site,
            pipeline=self.pipeline,
            input_type="local",
            input_config={"path": "/tmp/a"},
            output_type="local",
            output_config={"path": "/tmp/b"},
        )

    @override_settings(MAX_BACKFILL_DAYS=3)
    def test_enabled_site_gets_queued_and_dispatched(self):
        site = _site(enabled=True)
        self._assign(site)
        sched = DbScheduler.__new__(DbScheduler)  # skip Celery app wiring, only need the DB logic
        with patch("reduction.scheduler.reduce_period.delay") as mock_delay:
            sched._create_pending_periods(site)
        self.assertGreater(mock_delay.call_count, 0)
        statuses = set(ReductionPeriod.objects.filter(site=site).values_list("status", flat=True))
        self.assertEqual(statuses, {"QUEUED"})

    @override_settings(MAX_BACKFILL_DAYS=3)
    def test_disabled_site_gets_pending_rows_but_no_dispatch(self):
        site = _site(name="S2", enabled=False)
        self._assign(site)
        sched = DbScheduler.__new__(DbScheduler)
        with patch("reduction.scheduler.reduce_period.delay") as mock_delay:
            sched._create_pending_periods(site)
        mock_delay.assert_not_called()
        statuses = set(ReductionPeriod.objects.filter(site=site).values_list("status", flat=True))
        self.assertEqual(statuses, {"PENDING"})

    @override_settings(MAX_BACKFILL_DAYS=3)
    def test_tick_is_idempotent(self):
        site = _site(name="S3", enabled=True)
        self._assign(site)
        sched = DbScheduler.__new__(DbScheduler)
        with patch("reduction.scheduler.reduce_period.delay"):
            sched._create_pending_periods(site)
            first_count = ReductionPeriod.objects.filter(site=site).count()
            sched._create_pending_periods(site)
            second_count = ReductionPeriod.objects.filter(site=site).count()
        self.assertEqual(first_count, second_count)
