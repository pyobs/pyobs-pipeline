import datetime as dt
from unittest.mock import AsyncMock, patch

from django.test import TestCase

from reduction.models import Pipeline, PipelineStep, ReductionPeriod, Site, SitePipeline
from reduction.tasks import build_reduction_config, reduce_period


class BuildReductionConfigTests(TestCase):
    def setUp(self):
        self.site = Site.objects.create(name="S1", lat=0, lon=0, timezone="UTC")
        self.pipeline = Pipeline.objects.create(name="P1", period_config={"min_flats": 5})
        PipelineStep.objects.create(
            pipeline=self.pipeline, order=0, step_class="pyobs.images.processors.image.Flip", config={"flip_x": True}
        )
        self.period = ReductionPeriod.objects.create(site=self.site, date=dt.date(2026, 8, 1))

    def test_local_io(self):
        SitePipeline.objects.create(
            site=self.site,
            pipeline=self.pipeline,
            input_type="local",
            input_config={"path": "/data/raw"},
            output_type="local",
            output_config={"path": "/data/reduced"},
        )
        config = build_reduction_config(self.period)
        self.assertEqual(config["class"], "pyobs.utils.pipeline.Reduction")
        self.assertEqual(config["min_flats"], 5)
        self.assertEqual(config["archive"], {"class": "pyobs.robotic.utils.archive.LocalArchive", "root": "/data/raw"})
        self.assertEqual(config["output"], "/data/reduced")
        self.assertEqual(
            config["pipeline"],
            {
                "class": "pyobs.utils.pipeline.Pipeline",
                "steps": [{"class": "pyobs.images.processors.image.Flip", "flip_x": True}],
            },
        )

    def test_archive_io_passed_through(self):
        archive_config = {"class": "pyobs.robotic.utils.archive.PyobsArchive", "url": "http://x", "token": "t"}
        SitePipeline.objects.create(
            site=self.site,
            pipeline=self.pipeline,
            input_type="archive",
            input_config=archive_config,
            output_type="archive",
            output_config=archive_config,
        )
        config = build_reduction_config(self.period)
        self.assertEqual(config["archive"], archive_config)
        self.assertEqual(config["output"], archive_config)


class ReducePeriodTaskTests(TestCase):
    def setUp(self):
        self.site = Site.objects.create(name="S1", lat=0, lon=0, timezone="UTC")
        pipeline = Pipeline.objects.create(name="P1")
        PipelineStep.objects.create(pipeline=pipeline, order=0, step_class="pyobs.images.processors.image.Flip")
        SitePipeline.objects.create(
            site=self.site,
            pipeline=pipeline,
            input_type="local",
            input_config={"path": "/tmp/a"},
            output_type="local",
            output_config={"path": "/tmp/b"},
        )
        self.period = ReductionPeriod.objects.create(site=self.site, date=dt.date(2026, 8, 1), status="PENDING")

    @patch("reduction.tasks.create_object")
    def test_success_marks_completed(self, mock_create_object):
        mock_create_object.return_value = AsyncMock()
        reduce_period(self.site.id, self.period.id)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, "COMPLETED")
        self.assertIsNotNone(self.period.started_at)
        self.assertIsNotNone(self.period.finished_at)

    @patch("reduction.tasks.create_object")
    def test_exception_marks_failed_and_logs_traceback(self, mock_create_object):
        mock_create_object.return_value = AsyncMock(side_effect=RuntimeError("boom"))
        reduce_period(self.site.id, self.period.id)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, "FAILED")
        self.assertIn("RuntimeError", self.period.logs)
        self.assertIn("boom", self.period.logs)

    @patch("reduction.tasks.create_object")
    def test_running_status_set_before_call(self, mock_create_object):
        # create_object() runs synchronously (same thread/transaction as the test), so
        # reading status here -- rather than inside the awaited reduction() call, which
        # would need sync_to_async and is flaky nested inside TestCase's transaction --
        # is enough to confirm status=RUNNING was saved before the reduction runs.
        seen_status = {}

        def fake_create_object(config):
            seen_status["status"] = ReductionPeriod.objects.get(pk=self.period.pk).status
            return AsyncMock()

        mock_create_object.side_effect = fake_create_object

        reduce_period(self.site.id, self.period.id)
        self.assertEqual(seen_status["status"], "RUNNING")
