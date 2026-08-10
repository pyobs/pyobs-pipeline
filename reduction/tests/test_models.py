import datetime as dt

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from reduction.models import Pipeline, PipelineStep, ReductionPeriod, Site, SitePipeline


class SiteModelTests(TestCase):
    def test_create_and_str(self):
        site = Site.objects.create(name="Sutherland", lat=-32.38, lon=20.81, timezone="Africa/Johannesburg")
        self.assertEqual(str(site), "Sutherland")
        self.assertTrue(site.enabled)
        self.assertEqual(site.trigger_type, "sunrise")
        self.assertEqual(site.delay_hours, 3.0)

    def test_name_unique(self):
        Site.objects.create(name="Sutherland", lat=0, lon=0, timezone="UTC")
        with self.assertRaises(IntegrityError):
            Site.objects.create(name="Sutherland", lat=1, lon=1, timezone="UTC")

    def test_name_rejects_slash(self):
        """name is used directly as a URL path segment (sites/<str:name>/) -- a "/" in
        it breaks routing entirely (confirmed live: NoReverseMatch on every page linking
        to the site)."""
        site = Site(name="MONET/S", lat=0, lon=0, timezone="UTC")
        with self.assertRaises(ValidationError):
            site.full_clean()

    def test_siteid_defaults_blank(self):
        site = Site.objects.create(name="Sutherland", lat=0, lon=0, timezone="UTC")
        self.assertEqual(site.siteid, "")


class PipelineModelTests(TestCase):
    def test_create_and_str(self):
        pipeline = Pipeline.objects.create(name="Standard", period_config={"min_flats": 5})
        self.assertEqual(str(pipeline), "Standard")
        self.assertEqual(pipeline.period_config["min_flats"], 5)


class PipelineStepModelTests(TestCase):
    def test_ordering(self):
        pipeline = Pipeline.objects.create(name="Standard")
        PipelineStep.objects.create(pipeline=pipeline, order=1, step_class="b.B")
        PipelineStep.objects.create(pipeline=pipeline, order=0, step_class="a.A")
        self.assertEqual([s.step_class for s in pipeline.steps.all()], ["a.A", "b.B"])

    def test_str(self):
        pipeline = Pipeline.objects.create(name="Standard")
        step = PipelineStep.objects.create(pipeline=pipeline, order=0, step_class="pkg.Cls")
        self.assertEqual(str(step), "Standard[0]: pkg.Cls")


class SitePipelineModelTests(TestCase):
    def test_one_site_one_assignment(self):
        site = Site.objects.create(name="S1", lat=0, lon=0, timezone="UTC")
        pipeline = Pipeline.objects.create(name="P1")
        SitePipeline.objects.create(site=site, pipeline=pipeline)
        with self.assertRaises(IntegrityError):
            SitePipeline.objects.create(site=site, pipeline=pipeline)

    def test_related_names(self):
        site = Site.objects.create(name="S1", lat=0, lon=0, timezone="UTC")
        pipeline = Pipeline.objects.create(name="P1")
        assignment = SitePipeline.objects.create(site=site, pipeline=pipeline)
        self.assertEqual(site.pipeline_assignment, assignment)
        self.assertIn(assignment, pipeline.site_assignments.all())


class ReductionPeriodModelTests(TestCase):
    def test_create_defaults_and_str(self):
        site = Site.objects.create(name="S1", lat=0, lon=0, timezone="UTC")
        period = ReductionPeriod.objects.create(site=site, date=dt.date(2026, 8, 1))
        self.assertEqual(period.status, "PENDING")
        self.assertEqual(period.logs, "")
        self.assertIn("S1", str(period))
        self.assertIn("2026-08-01", str(period))

    def test_ordering_most_recent_first(self):
        site = Site.objects.create(name="S1", lat=0, lon=0, timezone="UTC")
        ReductionPeriod.objects.create(site=site, date=dt.date(2026, 8, 1))
        ReductionPeriod.objects.create(site=site, date=dt.date(2026, 8, 3))
        ReductionPeriod.objects.create(site=site, date=dt.date(2026, 8, 2))
        dates = list(site.periods.values_list("date", flat=True))
        self.assertEqual(dates, [dt.date(2026, 8, 3), dt.date(2026, 8, 2), dt.date(2026, 8, 1)])
