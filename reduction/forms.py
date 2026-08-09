from django import forms

from reduction.models import Pipeline, Site, SitePipeline


class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = [
            "name",
            "lat",
            "lon",
            "timezone",
            "enabled",
            "trigger_type",
            "delay_hours",
            "trigger_time",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "lat": forms.NumberInput(attrs={"class": "form-control", "step": "any"}),
            "lon": forms.NumberInput(attrs={"class": "form-control", "step": "any"}),
            "timezone": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Europe/Berlin"}),
            "enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "trigger_type": forms.Select(attrs={"class": "form-select"}),
            "delay_hours": forms.NumberInput(attrs={"class": "form-control", "step": "any"}),
            "trigger_time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
        }


ARCHIVE_CLASS = "pyobs.robotic.utils.archive.PyobsArchive"


class SitePipelineForm(forms.Form):
    """Not a ModelForm: input_config/output_config are JSONFields on SitePipeline, but
    editing them as raw JSON is error-prone -- this renders type-appropriate fields
    (a path for "local", url+token for "archive") and assembles the dicts itself. See
    from_instance()/apply_to() for the two directions of that conversion."""

    pipeline = forms.ModelChoiceField(
        queryset=Pipeline.objects.all(), widget=forms.Select(attrs={"class": "form-select"})
    )

    input_type = forms.ChoiceField(choices=SitePipeline.IO_TYPES, widget=forms.Select(attrs={"class": "form-select"}))
    input_path = forms.CharField(
        required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "/data/raw"})
    )
    input_url = forms.CharField(
        required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "http://archive.example.org"})
    )
    input_token = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))

    output_type = forms.ChoiceField(choices=SitePipeline.IO_TYPES, widget=forms.Select(attrs={"class": "form-select"}))
    output_path = forms.CharField(
        required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "/data/reduced"})
    )
    output_url = forms.CharField(
        required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "http://archive.example.org"})
    )
    output_token = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))

    @classmethod
    def from_instance(cls, assignment: SitePipeline | None) -> "SitePipelineForm":
        if assignment is None:
            return cls()
        return cls(
            initial={
                "pipeline": assignment.pipeline_id,
                "input_type": assignment.input_type,
                "input_path": assignment.input_config.get("path", ""),
                "input_url": assignment.input_config.get("url", ""),
                "input_token": assignment.input_config.get("token", ""),
                "output_type": assignment.output_type,
                "output_path": assignment.output_config.get("path", ""),
                "output_url": assignment.output_config.get("url", ""),
                "output_token": assignment.output_config.get("token", ""),
            }
        )

    def clean(self):
        cleaned = super().clean()
        for side in ("input", "output"):
            if cleaned.get(f"{side}_type") == "local" and not cleaned.get(f"{side}_path"):
                self.add_error(f"{side}_path", "Required for a local directory.")
            if cleaned.get(f"{side}_type") == "archive" and not cleaned.get(f"{side}_url"):
                self.add_error(f"{side}_url", "Required for a PyobsArchive.")
        return cleaned

    def _io_config(self, side: str) -> dict:
        if self.cleaned_data[f"{side}_type"] == "local":
            return {"path": self.cleaned_data[f"{side}_path"]}
        return {"class": ARCHIVE_CLASS, "url": self.cleaned_data[f"{side}_url"], "token": self.cleaned_data[f"{side}_token"]}

    def apply_to(self, site) -> SitePipeline:
        assignment, _ = SitePipeline.objects.update_or_create(
            site=site,
            defaults={
                "pipeline": self.cleaned_data["pipeline"],
                "input_type": self.cleaned_data["input_type"],
                "input_config": self._io_config("input"),
                "output_type": self.cleaned_data["output_type"],
                "output_config": self._io_config("output"),
            },
        )
        return assignment


class PipelineForm(forms.ModelForm):
    class Meta:
        model = Pipeline
        fields = ["name", "description", "period_config"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "period_config": forms.Textarea(attrs={"class": "form-control font-monospace", "rows": 4}),
        }
        help_texts = {
            "period_config": "kwargs for the top-level reduction object, e.g. min_flats, filenames_calib, create_calibs, calib_science",
        }
