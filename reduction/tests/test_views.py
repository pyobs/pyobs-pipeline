import datetime as dt
import json
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from django.urls import reverse

from reduction.models import Pipeline, PipelineStep, ReductionPeriod, Site, SitePipeline

TEST_PASSWORD_HASH = make_password("testpass")


@override_settings(ADMIN_USERNAME="admin", ADMIN_PASSWORD_HASH=TEST_PASSWORD_HASH)
class AuthenticatedTestCase(TestCase):
    def setUp(self):
        self.client.post(reverse("login"), {"username": "admin", "password": "testpass", "next": "/"})


class LoginRequiredTests(TestCase):
    @override_settings(ADMIN_USERNAME="admin", ADMIN_PASSWORD_HASH=TEST_PASSWORD_HASH)
    def test_dashboard_redirects_when_not_logged_in(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/login/"))

    @override_settings(ADMIN_USERNAME="admin", ADMIN_PASSWORD_HASH=TEST_PASSWORD_HASH)
    def test_login_then_dashboard(self):
        self.client.post(reverse("login"), {"username": "admin", "password": "testpass", "next": "/"})
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

    @override_settings(ADMIN_USERNAME="admin", ADMIN_PASSWORD_HASH=TEST_PASSWORD_HASH)
    def test_wrong_password_rejected(self):
        response = self.client.post(reverse("login"), {"username": "admin", "password": "wrong", "next": "/"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid username or password")


class SiteViewTests(AuthenticatedTestCase):
    def test_add_edit_delete_flow(self):
        response = self.client.post(
            reverse("site_add"),
            {
                "name": "S1",
                "lat": 51.5,
                "lon": 9.9,
                "timezone": "Europe/Berlin",
                "enabled": "on",
                "trigger_type": "sunrise",
                "delay_hours": 3.0,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Site.objects.filter(name="S1").exists())

        response = self.client.get(reverse("site_detail", args=["S1"]))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("site_edit", args=["S1"]),
            {
                "name": "S1",
                "lat": 52.0,
                "lon": 10.0,
                "timezone": "Europe/Berlin",
                "trigger_type": "fixed_time",
                "delay_hours": 3.0,
                "trigger_time": "22:00",
            },
        )
        self.assertEqual(response.status_code, 302)
        site = Site.objects.get(name="S1")
        self.assertEqual(site.trigger_type, "fixed_time")
        self.assertFalse(site.enabled)  # checkbox omitted on edit POST -> False

        response = self.client.post(reverse("site_delete", args=["S1"]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Site.objects.filter(name="S1").exists())

    def test_site_pipeline_assignment_form_local(self):
        site = Site.objects.create(name="S1", lat=0, lon=0, timezone="UTC")
        pipeline = Pipeline.objects.create(name="P1")
        response = self.client.post(
            reverse("site_detail", args=["S1"]),
            {
                "pipeline": pipeline.pk,
                "input_type": "local",
                "input_path": "/data/raw",
                "output_type": "local",
                "output_path": "/data/reduced",
            },
        )
        self.assertEqual(response.status_code, 302)
        assignment = SitePipeline.objects.get(site=site, pipeline=pipeline)
        self.assertEqual(assignment.input_config, {"path": "/data/raw"})
        self.assertEqual(assignment.output_config, {"path": "/data/reduced"})

    def test_site_pipeline_assignment_form_archive(self):
        site = Site.objects.create(name="S1", lat=0, lon=0, timezone="UTC")
        pipeline = Pipeline.objects.create(name="P1")
        response = self.client.post(
            reverse("site_detail", args=["S1"]),
            {
                "pipeline": pipeline.pk,
                "input_type": "archive",
                "input_url": "http://archive.example.org",
                "input_token": "secret",
                "output_type": "archive",
                "output_url": "http://archive.example.org",
                "output_token": "secret",
            },
        )
        self.assertEqual(response.status_code, 302)
        assignment = SitePipeline.objects.get(site=site, pipeline=pipeline)
        self.assertEqual(
            assignment.input_config,
            {"class": "pyobs.robotic.utils.archive.PyobsArchive", "url": "http://archive.example.org", "token": "secret"},
        )

    def test_site_pipeline_assignment_form_missing_required_field(self):
        site = Site.objects.create(name="S1", lat=0, lon=0, timezone="UTC")
        pipeline = Pipeline.objects.create(name="P1")
        response = self.client.post(
            reverse("site_detail", args=["S1"]),
            {"pipeline": pipeline.pk, "input_type": "local", "output_type": "local", "output_path": "/data/reduced"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Required for a local directory")
        self.assertFalse(SitePipeline.objects.filter(site=site).exists())

    def test_site_pipeline_assignment_updates_existing(self):
        site = Site.objects.create(name="S1", lat=0, lon=0, timezone="UTC")
        pipeline = Pipeline.objects.create(name="P1")
        SitePipeline.objects.create(
            site=site, pipeline=pipeline, input_type="local", input_config={"path": "/old"},
            output_type="local", output_config={"path": "/old-out"},
        )
        self.client.post(
            reverse("site_detail", args=["S1"]),
            {
                "pipeline": pipeline.pk,
                "input_type": "local",
                "input_path": "/new",
                "output_type": "local",
                "output_path": "/new-out",
            },
        )
        self.assertEqual(SitePipeline.objects.filter(site=site).count(), 1)
        assignment = SitePipeline.objects.get(site=site)
        self.assertEqual(assignment.input_config, {"path": "/new"})


class PipelineBuilderViewTests(AuthenticatedTestCase):
    def test_add_configure_reorder_delete_step(self):
        response = self.client.post(reverse("pipeline_add"), {"name": "P1", "description": "", "period_config": "{}"})
        self.assertEqual(response.status_code, 302)
        pipeline = Pipeline.objects.get(name="P1")

        response = self.client.post(
            reverse("pipeline_step_add", args=["P1"]), {"step_class": "pyobs.images.processors.image.Flip"}
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            reverse("pipeline_step_add", args=["P1"]), {"custom_step_class": "pyobs.images.processors.image.SoftBin"}
        )
        self.assertEqual(response.status_code, 302)
        steps = list(pipeline.steps.all())
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].order, 0)
        self.assertEqual(steps[1].order, 1)

        flip = steps[0]
        response = self.client.post(
            reverse("pipeline_step_config", args=["P1", flip.pk]), {"field_flip_x": "on"}
        )
        self.assertEqual(response.status_code, 302)
        flip.refresh_from_db()
        self.assertEqual(flip.config, {"flip_x": True, "flip_y": False})

        response = self.client.post(
            reverse("pipeline_step_reorder", args=["P1"]),
            data=json.dumps({"order": [steps[1].pk, steps[0].pk]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        steps[1].refresh_from_db()
        steps[0].refresh_from_db()
        self.assertEqual(steps[1].order, 0)
        self.assertEqual(steps[0].order, 1)

        response = self.client.post(reverse("pipeline_step_delete", args=["P1", flip.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(pipeline.steps.count(), 1)

    def test_add_step_rejects_unimportable_class(self):
        self.client.post(reverse("pipeline_add"), {"name": "P1", "description": "", "period_config": "{}"})
        response = self.client.post(
            reverse("pipeline_step_add", args=["P1"]), {"custom_step_class": "pyobs.does.not.Exist"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Pipeline.objects.get(name="P1").steps.count(), 0)


class PeriodViewTests(AuthenticatedTestCase):
    def _make_site_with_pipeline(self, name="S1", enabled=True):
        site = Site.objects.create(name=name, lat=0, lon=0, timezone="UTC", enabled=enabled)
        pipeline = Pipeline.objects.create(name=f"P-{name}")
        PipelineStep.objects.create(pipeline=pipeline, order=0, step_class="pyobs.images.processors.image.Flip")
        SitePipeline.objects.create(
            site=site,
            pipeline=pipeline,
            input_type="local",
            input_config={"path": "/tmp/a"},
            output_type="local",
            output_config={"path": "/tmp/b"},
        )
        return site

    def test_period_list_filters(self):
        site = self._make_site_with_pipeline()
        ReductionPeriod.objects.create(site=site, date=dt.date(2026, 8, 1), status="COMPLETED")
        ReductionPeriod.objects.create(site=site, date=dt.date(2026, 8, 2), status="FAILED")

        response = self.client.get(reverse("period_list"), {"status": "FAILED"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["periods"].values_list("status", flat=True)), ["FAILED"])

    @patch("reduction.period_actions.reduce_period.delay")
    def test_start_on_enabled_site(self, mock_delay):
        mock_delay.return_value.id = "task-123"
        site = self._make_site_with_pipeline(enabled=True)
        period = ReductionPeriod.objects.create(site=site, date=dt.date(2026, 8, 1), status="PENDING")

        response = self.client.post(reverse("period_start", args=[period.pk]))
        self.assertEqual(response.status_code, 302)
        period.refresh_from_db()
        self.assertEqual(period.status, "QUEUED")
        self.assertEqual(period.task_id, "task-123")
        mock_delay.assert_called_once_with(site.id, period.id)

    @patch("reduction.period_actions.reduce_period.delay")
    def test_start_on_disabled_site_still_works_manually(self, mock_delay):
        mock_delay.return_value.id = "task-456"
        site = self._make_site_with_pipeline(enabled=False)
        period = ReductionPeriod.objects.create(site=site, date=dt.date(2026, 8, 1), status="PENDING")

        response = self.client.post(reverse("period_start", args=[period.pk]))
        self.assertEqual(response.status_code, 302)
        period.refresh_from_db()
        self.assertEqual(period.status, "QUEUED")
        mock_delay.assert_called_once()

    def test_start_rejected_when_conflicting_period_active(self):
        site = self._make_site_with_pipeline()
        ReductionPeriod.objects.create(site=site, date=dt.date(2026, 8, 1), status="RUNNING")
        pending = ReductionPeriod.objects.create(site=site, date=dt.date(2026, 8, 1), status="PENDING")

        response = self.client.post(reverse("period_start", args=[pending.pk]))
        self.assertEqual(response.status_code, 400)
        pending.refresh_from_db()
        self.assertEqual(pending.status, "PENDING")

    @patch("reduction.period_actions.AsyncResult")
    def test_stop_revokes_and_cancels(self, mock_async_result):
        site = self._make_site_with_pipeline()
        period = ReductionPeriod.objects.create(
            site=site, date=dt.date(2026, 8, 1), status="RUNNING", task_id="task-789"
        )
        response = self.client.post(reverse("period_stop", args=[period.pk]))
        self.assertEqual(response.status_code, 302)
        mock_async_result.assert_called_once_with("task-789")
        mock_async_result.return_value.revoke.assert_called_once_with(terminate=True)
        period.refresh_from_db()
        self.assertEqual(period.status, "CANCELLED")
        self.assertIn("Cancelled by operator", period.logs)

    def test_stop_rejected_when_not_running(self):
        site = self._make_site_with_pipeline()
        period = ReductionPeriod.objects.create(site=site, date=dt.date(2026, 8, 1), status="PENDING")
        response = self.client.post(reverse("period_stop", args=[period.pk]))
        self.assertEqual(response.status_code, 400)

    def test_reset_cancels_stuck_period_without_revoke(self):
        site = self._make_site_with_pipeline()
        period = ReductionPeriod.objects.create(
            site=site, date=dt.date(2026, 8, 1), status="QUEUED", task_id="orphaned"
        )
        with patch("reduction.period_actions.AsyncResult") as mock_async_result:
            response = self.client.post(reverse("period_reset", args=[period.pk]))
            mock_async_result.assert_not_called()
        self.assertEqual(response.status_code, 302)
        period.refresh_from_db()
        self.assertEqual(period.status, "CANCELLED")

    @patch("reduction.period_actions.reduce_period.delay")
    def test_restart_creates_fresh_row_for_same_site_date(self, mock_delay):
        mock_delay.return_value.id = "new-task"
        site = self._make_site_with_pipeline()
        period = ReductionPeriod.objects.create(
            site=site, date=dt.date(2026, 8, 1), status="RUNNING", task_id="old-task"
        )
        with patch("reduction.period_actions.AsyncResult"):
            response = self.client.post(reverse("period_restart", args=[period.pk]))
        self.assertEqual(response.status_code, 302)

        period.refresh_from_db()
        self.assertEqual(period.status, "CANCELLED")
        new_period = ReductionPeriod.objects.exclude(pk=period.pk).get(site=site, date=dt.date(2026, 8, 1))
        self.assertEqual(new_period.status, "QUEUED")
        self.assertEqual(ReductionPeriod.objects.filter(site=site, date=dt.date(2026, 8, 1)).count(), 2)

    def test_status_api_returns_json(self):
        site = self._make_site_with_pipeline()
        period = ReductionPeriod.objects.create(site=site, date=dt.date(2026, 8, 1), status="RUNNING", logs="line1")
        response = self.client.get(reverse("period_status_api", args=[period.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "RUNNING")
        self.assertEqual(data["logs"], "line1")
