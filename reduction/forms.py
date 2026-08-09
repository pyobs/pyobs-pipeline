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


class SitePipelineForm(forms.ModelForm):
    class Meta:
        model = SitePipeline
        fields = [
            "pipeline",
            "input_type",
            "input_config",
            "output_type",
            "output_config",
        ]
        widgets = {
            "pipeline": forms.Select(attrs={"class": "form-select"}),
            "input_type": forms.Select(attrs={"class": "form-select"}),
            "input_config": forms.Textarea(attrs={"class": "form-control font-monospace", "rows": 4}),
            "output_type": forms.Select(attrs={"class": "form-select"}),
            "output_config": forms.Textarea(attrs={"class": "form-control font-monospace", "rows": 4}),
        }


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
