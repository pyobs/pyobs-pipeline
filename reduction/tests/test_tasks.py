import datetime as dt
import logging
from unittest.mock import AsyncMock, patch

from django.test import TestCase, TransactionTestCase

from pyobs.utils.enums import ImageType
from pyobs.utils.pipeline import MasterCalibCreated, ScienceFrameProcessed
from reduction.models import Pipeline, PipelineStep, ReductionPeriod, Site, SitePipeline
from reduction.tasks import _Flusher, _LogCollector, _ProgressCollector, build_reduction_config, reduce_period


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


class CalibrationArchivePropagationTests(TestCase):
    """A Calibration step doesn't need to repeat the site's archive in its own config --
    pyobs-core's Pipeline forwards its archive to steps that don't specify their own
    (see pyobs.mixins.pipeline.PipelineMixin). This locks that integration in from the
    pyobs-pipeline side, using the real pyobs-core classes end to end (no mocking)."""

    def test_calibration_step_without_own_archive_gets_site_archive(self):
        from pyobs.object import create_object

        site = Site.objects.create(name="S1", lat=0, lon=0, timezone="UTC")
        pipeline = Pipeline.objects.create(name="P1")
        PipelineStep.objects.create(
            pipeline=pipeline,
            order=0,
            step_class="pyobs.images.processors.calibration.Calibration",
            config={"require_bias": False, "require_dark": False, "require_flat": False},
        )
        SitePipeline.objects.create(
            site=site,
            pipeline=pipeline,
            input_type="local",
            input_config={"path": "/tmp/raw"},
            output_type="local",
            output_config={"path": "/tmp/reduced"},
        )
        period = ReductionPeriod.objects.create(site=site, date=dt.date(2026, 8, 1))

        config = build_reduction_config(period)
        self.assertNotIn("archive", config["pipeline"]["steps"][0])

        reduction = create_object(config)
        calibration_step = reduction._pipeline._PipelineMixin__pipeline_steps[0]
        self.assertEqual(calibration_step._archive.root, "/tmp/raw")


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
    def test_calls_reduction_with_siteid_not_display_name(self, mock_create_object):
        """The archive doesn't necessarily know a site by its pyobs-pipeline display
        name (e.g. "Sutherland" vs. the archive's own "monets") -- siteid, when set,
        must be what's actually passed to Reduction.__call__."""
        self.site.siteid = "monets"
        self.site.save()
        mock_reduction = AsyncMock()
        mock_create_object.return_value = mock_reduction

        reduce_period(self.site.id, self.period.id)

        mock_reduction.assert_called_once_with("monets", "2026-08-01")

    @patch("reduction.tasks.create_object")
    def test_falls_back_to_display_name_when_siteid_unset(self, mock_create_object):
        mock_reduction = AsyncMock()
        mock_create_object.return_value = mock_reduction

        reduce_period(self.site.id, self.period.id)

        mock_reduction.assert_called_once_with("S1", "2026-08-01")

    @patch("reduction.tasks.create_object")
    def test_exception_marks_failed_and_logs_traceback(self, mock_create_object):
        mock_create_object.return_value = AsyncMock(side_effect=RuntimeError("boom"))
        reduce_period(self.site.id, self.period.id)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, "FAILED")
        self.assertIn("RuntimeError", self.period.logs)
        self.assertIn("boom", self.period.logs)

    @patch("reduction.tasks.create_object")
    def test_progress_callback_passed_to_create_object(self, mock_create_object):
        mock_create_object.return_value = AsyncMock()
        reduce_period(self.site.id, self.period.id)
        _, kwargs = mock_create_object.call_args
        self.assertIn("progress_callback", kwargs)
        self.assertTrue(callable(kwargs["progress_callback"]))

    @patch("reduction.tasks.create_object")
    def test_progress_saved_on_completion(self, mock_create_object):
        async def fake_call(*args, **kwargs):
            callback = mock_create_object.call_args.kwargs["progress_callback"]
            callback(MasterCalibCreated(ImageType.BIAS, "cam1", "1x1", None, "bias.fits"))
            callback(ScienceFrameProcessed(1, 2, "obj0.fits", "ok"))
            callback(ScienceFrameProcessed(2, 2, "obj1.fits", "error", "boom"))

        mock_create_object.return_value = AsyncMock(side_effect=fake_call)
        reduce_period(self.site.id, self.period.id)

        self.period.refresh_from_db()
        self.assertEqual(len(self.period.progress["calibs"]), 1)
        self.assertEqual(self.period.progress["calibs"][0]["filename"], "bias.fits")
        self.assertEqual(self.period.progress["frames"]["total"], 2)
        self.assertEqual(len(self.period.progress["frames"]["items"]), 2)
        self.assertEqual(self.period.progress["frames"]["items"][1]["status"], "error")

    @patch("reduction.tasks.create_object")
    def test_running_status_set_before_call(self, mock_create_object):
        # create_object() runs synchronously (same thread/transaction as the test), so
        # reading status here -- rather than inside the awaited reduction() call, which
        # would need sync_to_async and is flaky nested inside TestCase's transaction --
        # is enough to confirm status=RUNNING was saved before the reduction runs.
        seen_status = {}

        def fake_create_object(config, **kwargs):
            seen_status["status"] = ReductionPeriod.objects.get(pk=self.period.pk).status
            return AsyncMock()

        mock_create_object.side_effect = fake_create_object

        reduce_period(self.site.id, self.period.id)
        self.assertEqual(seen_status["status"], "RUNNING")


class FlusherTests(TransactionTestCase):
    """Uses TransactionTestCase, not TestCase: the flush runs on a real background
    thread with its own DB connection, and a plain TestCase's uncommitted transaction
    on the main-thread connection wouldn't be visible to it.

    _LogCollector and _ProgressCollector share one _Flusher (see tasks.py's docstring on
    _Flusher for why: two independent flush threads racing to update the same row can hit
    "database table is locked"), so these are tested together via that shared flusher,
    matching how reduce_period actually wires them up."""

    def setUp(self):
        self.site = Site.objects.create(name="S1", lat=0, lon=0, timezone="UTC")
        self.period = ReductionPeriod.objects.create(site=self.site, date=dt.date(2026, 8, 1), status="RUNNING")

    def _make_pipeline(self):
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

    def _make_flusher_pair(self, prior_logs: str = "") -> tuple[_LogCollector, _ProgressCollector, _Flusher]:
        def get_fields():
            return {"logs": handler.full_text, "progress": progress.data}

        flusher = _Flusher(self.period.pk, get_fields)
        handler = _LogCollector(prior_logs, flusher)
        handler.setFormatter(logging.Formatter("%(message)s"))
        progress = _ProgressCollector(flusher)
        return handler, progress, flusher

    def test_flush_writes_logs_and_progress_from_background_thread(self):
        handler, progress, flusher = self._make_flusher_pair()
        handler.lines.append("line one")
        progress.on_progress(MasterCalibCreated(ImageType.BIAS, "cam1", "1x1", None, "bias.fits"))
        flusher.flush()
        flusher.join(timeout=5)

        self.period.refresh_from_db()
        self.assertEqual(self.period.logs, "line one")
        self.assertEqual(self.period.progress["calibs"][0]["filename"], "bias.fits")

    def test_prior_logs_preserved_on_flush(self):
        handler, progress, flusher = self._make_flusher_pair(prior_logs="from an earlier run")
        handler.lines.append("new line")
        flusher.flush()
        flusher.join(timeout=5)

        self.period.refresh_from_db()
        self.assertEqual(self.period.logs, "from an earlier run\nnew line")

    def test_emit_throttles_flushes_within_the_interval(self):
        handler, _progress, flusher = self._make_flusher_pair()
        with patch.object(_Flusher, "FLUSH_INTERVAL", 100):  # effectively "never" for this test's duration
            handler.emit(logging.LogRecord("t", logging.INFO, "", 0, "first", None, None))
            first_thread = flusher._flush_thread
            handler.emit(logging.LogRecord("t", logging.INFO, "", 0, "second", None, None))
            self.assertIs(flusher._flush_thread, first_thread)  # no new flush triggered

    def test_on_progress_accumulates_calibs_and_frames(self):
        _handler, progress, _flusher = self._make_flusher_pair()
        progress.on_progress(MasterCalibCreated(ImageType.BIAS, "cam1", "1x1", None, "bias.fits"))
        progress.on_progress(MasterCalibCreated(ImageType.DARK, "cam1", "1x1", None, "dark.fits", exptime=600.0))
        progress.on_progress(ScienceFrameProcessed(1, 3, "obj0.fits", "ok"))

        self.assertEqual(len(progress.calibs), 2)
        self.assertIsNone(progress.calibs[0]["exptime"])
        self.assertEqual(progress.calibs[1]["exptime"], 600.0)
        self.assertEqual(
            progress.frames,
            {"total": 3, "items": [{"index": 1, "filename": "obj0.fits", "status": "ok", "error": None}]},
        )

    @patch("reduction.tasks.create_object")
    def test_reduce_period_survives_a_log_line_emitted_during_the_async_call(self, mock_create_object):
        """A synchronous ORM write triggered from inside asyncio.run()'s active event
        loop raises SynchronousOnlyOperation (confirmed empirically) -- the flusher's
        periodic flush must not do that directly. Forces an actual flush attempt
        mid-run by patching FLUSH_INTERVAL to 0, so any regression back to a direct
        write would fail this test with FAILED/SynchronousOnlyOperation in the logs
        instead of COMPLETED."""
        self._make_pipeline()
        self.period.status = "PENDING"
        self.period.save()

        async def fake_call(*args, **kwargs):
            # .warning(), not .info() -- the root logger's default level is WARNING,
            # and reduce_period doesn't lower it (matches production, where Celery's own
            # --loglevel flag is what makes INFO visible; not this test's concern).
            logging.getLogger("reduction.tests").warning("mid-run log line")
            callback = mock_create_object.call_args.kwargs["progress_callback"]
            callback(ScienceFrameProcessed(1, 1, "obj0.fits", "ok"))

        mock_create_object.return_value = AsyncMock(side_effect=fake_call)

        with patch.object(_Flusher, "FLUSH_INTERVAL", 0):
            reduce_period(self.site.id, self.period.id)

        self.period.refresh_from_db()
        self.assertEqual(self.period.status, "COMPLETED")
        self.assertIn("mid-run log line", self.period.logs)
        self.assertEqual(self.period.progress["frames"]["total"], 1)
