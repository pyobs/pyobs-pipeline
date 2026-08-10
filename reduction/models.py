from django.core.validators import RegexValidator
from django.db import models

# name is used directly as a URL path segment (sites/<str:name>/) -- a "/" in it breaks
# routing entirely (NoReverseMatch on every page linking to the site).
_no_slash_validator = RegexValidator(regex=r"^[^/]+$", message='Site name can\'t contain "/" -- it\'s used directly in URLs.')


class Site(models.Model):
    TRIGGER_TYPES = [
        ("sunrise", "Sunrise"),
        ("sunset", "Sunset"),
        ("fixed_time", "Fixed local time"),
    ]

    name = models.CharField(max_length=100, unique=True, validators=[_no_slash_validator])
    siteid = models.CharField(
        max_length=100,
        blank=True,
        help_text=(
            "Site code as known to the archive (e.g. \"monets\"), used when querying frames. "
            "Not necessarily the same as the display name above -- falls back to it if left blank."
        ),
    )
    lat = models.FloatField()
    lon = models.FloatField()
    timezone = models.CharField(max_length=64)
    enabled = models.BooleanField(default=True)
    trigger_type = models.CharField(max_length=20, choices=TRIGGER_TYPES, default="sunrise")
    delay_hours = models.FloatField(
        default=3.0, help_text="Offset after the trigger event; ignored for fixed_time"
    )
    trigger_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Local time of day to trigger; used only when trigger_type is fixed_time",
    )

    def __str__(self) -> str:
        return self.name


class Pipeline(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    # kwargs for the top-level reduction object: min_flats, filenames_calib,
    # create_calibs, calib_science
    period_config = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.name


class PipelineStep(models.Model):
    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name="steps")
    order = models.IntegerField()
    step_class = models.CharField(
        max_length=255, help_text="Dotted path, e.g. pyobs.images.processors.misc.Calibration"
    )
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        return f"{self.pipeline.name}[{self.order}]: {self.step_class}"


class SitePipeline(models.Model):
    IO_TYPES = [
        ("local", "Local directory"),
        ("archive", "PyobsArchive"),
    ]

    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name="pipeline_assignment")
    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name="site_assignments")
    input_type = models.CharField(max_length=10, choices=IO_TYPES, default="local")
    # e.g. {"path": "/data/raw"} or
    # {"class": "pyobs.robotic.utils.archive.PyobsArchive", "url": "...", "token": "..."}
    input_config = models.JSONField(default=dict, blank=True)
    output_type = models.CharField(max_length=10, choices=IO_TYPES, default="local")
    # e.g. {"path": "/data/reduced"} or
    # {"class": "pyobs.robotic.utils.archive.PyobsArchive", "url": "...", "token": "..."}
    output_config = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"{self.site.name} -> {self.pipeline.name}"


class ReductionPeriod(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),  # row exists, not yet dispatched (created by trigger event)
        ("QUEUED", "Queued"),
        ("RUNNING", "Running"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
        ("CANCELLED", "Cancelled"),  # manually stopped or reset
    ]

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="periods")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING")
    logs = models.TextField(blank=True)
    # {"calibs": [{"image_type", "instrument", "binning", "filter", "filename"}, ...],
    #  "frames": {"total": int, "items": [{"index", "filename", "status", "error"}, ...]}}
    progress = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    task_id = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.site.name} {self.date} ({self.status})"
