import json

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from pyobs.object import get_class_from_string
from reduction.forms import PipelineForm, SiteForm, SitePipelineForm
from reduction.models import Pipeline, PipelineStep, ReductionPeriod, Site, SitePipeline
from reduction.period_actions import PeriodActionError, reset_period, restart_period, start_period, stop_period
from reduction.step_fields import KNOWN_STEP_TEMPLATES, get_step_fields


def login_view(request):
    error = False
    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        if (
            username == settings.ADMIN_USERNAME
            and settings.ADMIN_PASSWORD_HASH
            and check_password(password, settings.ADMIN_PASSWORD_HASH)
        ):
            request.session["authenticated"] = True
            request.session["username"] = username
            return redirect(request.POST.get("next") or "/")
        error = True
    return render(
        request,
        "registration/login.html",
        {"error": error, "next": request.GET.get("next", "/")},
    )


def logout_view(request):
    if request.method == "POST":
        request.session.flush()
    return redirect("/login/")


def dashboard(request):
    return render(request, "reduction/dashboard.html")


# ── Sites ───────────────────────────────────────────────────────────────────

def site_list(request):
    sites = Site.objects.all().order_by("name")
    return render(request, "reduction/site_list.html", {"sites": sites})


def site_add(request):
    if request.method == "POST":
        form = SiteForm(request.POST)
        if form.is_valid():
            site = form.save()
            return redirect("site_detail", name=site.name)
    else:
        form = SiteForm()
    return render(request, "reduction/site_form.html", {"form": form, "site": None})


def site_edit(request, name: str):
    site = get_object_or_404(Site, name=name)
    if request.method == "POST":
        form = SiteForm(request.POST, instance=site)
        if form.is_valid():
            site = form.save()
            return redirect("site_detail", name=site.name)
    else:
        form = SiteForm(instance=site)
    return render(request, "reduction/site_form.html", {"form": form, "site": site})


def site_delete(request, name: str):
    site = get_object_or_404(Site, name=name)
    if request.method == "POST":
        site.delete()
        return redirect("site_list")
    return render(request, "reduction/site_confirm_delete.html", {"site": site})


def site_detail(request, name: str):
    site = get_object_or_404(Site, name=name)
    assignment = SitePipeline.objects.filter(site=site).first()

    if request.method == "POST":
        form = SitePipelineForm(request.POST, instance=assignment)
        if form.is_valid():
            sp = form.save(commit=False)
            sp.site = site
            sp.save()
            return redirect("site_detail", name=site.name)
    else:
        form = SitePipelineForm(instance=assignment)

    periods = site.periods.all()[:20]
    return render(
        request,
        "reduction/site_detail.html",
        {"site": site, "form": form, "assignment": assignment, "periods": periods},
    )


# ── Pipelines ───────────────────────────────────────────────────────────────

def pipeline_list(request):
    pipelines = Pipeline.objects.all().order_by("name")
    return render(request, "reduction/pipeline_list.html", {"pipelines": pipelines})


def pipeline_add(request):
    if request.method == "POST":
        form = PipelineForm(request.POST)
        if form.is_valid():
            pipeline = form.save()
            return redirect("pipeline_detail", name=pipeline.name)
    else:
        form = PipelineForm()
    return render(request, "reduction/pipeline_form.html", {"form": form, "pipeline": None})


def pipeline_edit(request, name: str):
    pipeline = get_object_or_404(Pipeline, name=name)
    if request.method == "POST":
        form = PipelineForm(request.POST, instance=pipeline)
        if form.is_valid():
            pipeline = form.save()
            return redirect("pipeline_detail", name=pipeline.name)
    else:
        form = PipelineForm(instance=pipeline)
    return render(request, "reduction/pipeline_form.html", {"form": form, "pipeline": pipeline})


def pipeline_delete(request, name: str):
    pipeline = get_object_or_404(Pipeline, name=name)
    if request.method == "POST":
        pipeline.delete()
        return redirect("pipeline_list")
    return render(request, "reduction/pipeline_confirm_delete.html", {"pipeline": pipeline})


def _step_field_values(fields: list[dict], data) -> tuple[dict, list[str]]:
    """Parse POSTed form values for a set of introspected step fields.

    Returns (config, errors) -- config only contains fields that parsed cleanly.
    """
    config: dict = {}
    errors: list[str] = []
    for field in fields:
        name = field["name"]
        raw = data.get(f"field_{name}")
        if field["type"] == "boolean":
            config[name] = data.get(f"field_{name}") is not None
            continue
        if raw is None or raw == "":
            if field["required"]:
                errors.append(f"{field['label']} is required.")
            continue
        if field["type"] == "integer":
            try:
                config[name] = int(raw)
            except ValueError:
                errors.append(f"{field['label']} must be an integer.")
        elif field["type"] == "number":
            try:
                config[name] = float(raw)
            except ValueError:
                errors.append(f"{field['label']} must be a number.")
        elif field["type"] == "json":
            try:
                config[name] = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(f"{field['label']}: invalid JSON ({exc}).")
        else:
            config[name] = raw
    return config, errors


def _build_step_views(pipeline: Pipeline, skip_step_id: int | None = None) -> list[dict]:
    """Introspected field definitions (pre-filled from saved config) for every step,
    skipping `skip_step_id` -- the caller fills that one in itself, e.g. with
    just-submitted (possibly invalid) values instead of the saved config."""
    step_views = []
    for step in pipeline.steps.all():
        if step.pk == skip_step_id:
            continue
        try:
            fields = get_step_fields(step.step_class)
            for field in fields:
                field["value"] = step.config.get(field["name"], field["default"])
                if field["type"] == "json" and field["value"] is not None:
                    field["value"] = json.dumps(field["value"])
            error = None
        except Exception as exc:
            fields = None
            error = str(exc)
        step_views.append({"step": step, "fields": fields, "error": error})
    return step_views


def pipeline_detail(request, name: str):
    pipeline = get_object_or_404(Pipeline, name=name)
    return render(
        request,
        "reduction/pipeline_detail.html",
        {
            "pipeline": pipeline,
            "step_views": _build_step_views(pipeline),
            "known_templates": KNOWN_STEP_TEMPLATES,
        },
    )


@require_POST
def pipeline_step_add(request, name: str):
    pipeline = get_object_or_404(Pipeline, name=name)
    step_class = (request.POST.get("step_class") or request.POST.get("custom_step_class") or "").strip()

    try:
        get_class_from_string(step_class)
    except Exception as exc:
        return render(
            request,
            "reduction/pipeline_detail.html",
            {
                "pipeline": pipeline,
                "step_views": _build_step_views(pipeline),
                "known_templates": KNOWN_STEP_TEMPLATES,
                "add_step_error": f"Could not import '{step_class}': {exc}",
            },
            status=400,
        )

    max_order = pipeline.steps.count()
    PipelineStep.objects.create(pipeline=pipeline, order=max_order, step_class=step_class, config={})
    return redirect("pipeline_detail", name=pipeline.name)


@require_POST
def pipeline_step_config(request, name: str, step_id: int):
    pipeline = get_object_or_404(Pipeline, name=name)
    step = get_object_or_404(PipelineStep, pk=step_id, pipeline=pipeline)

    fields = get_step_fields(step.step_class)
    config, errors = _step_field_values(fields, request.POST)
    if not errors:
        step.config = config
        step.save()
        return redirect("pipeline_detail", name=pipeline.name)

    for field in fields:
        field["value"] = request.POST.get(f"field_{field['name']}", field["default"])
    step_views = _build_step_views(pipeline, skip_step_id=step.pk)
    step_views.insert(
        next((i for i, sv in enumerate(step_views) if sv["step"].order > step.order), len(step_views)),
        {"step": step, "fields": fields, "error": None},
    )

    return render(
        request,
        "reduction/pipeline_detail.html",
        {
            "pipeline": pipeline,
            "step_views": step_views,
            "known_templates": KNOWN_STEP_TEMPLATES,
            "config_errors": errors,
        },
        status=400,
    )


@require_POST
def pipeline_step_delete(request, name: str, step_id: int):
    pipeline = get_object_or_404(Pipeline, name=name)
    step = get_object_or_404(PipelineStep, pk=step_id, pipeline=pipeline)
    step.delete()
    for i, s in enumerate(pipeline.steps.all()):
        if s.order != i:
            s.order = i
            s.save(update_fields=["order"])
    return redirect("pipeline_detail", name=pipeline.name)


@require_POST
def pipeline_step_reorder(request, name: str):
    pipeline = get_object_or_404(Pipeline, name=name)
    try:
        ordered_ids = json.loads(request.body)["order"]
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({"error": "invalid payload"}, status=400)

    steps_by_id = {s.pk: s for s in pipeline.steps.all()}
    for order, step_id in enumerate(ordered_ids):
        step = steps_by_id.get(int(step_id))
        if step is not None and step.order != order:
            step.order = order
            step.save(update_fields=["order"])
    return JsonResponse({"ok": True})


# ── Reduction periods ─────────────────────────────────────────────────────────

def period_list(request):
    periods = ReductionPeriod.objects.select_related("site").all()
    site_filter = request.GET.get("site", "")
    status_filter = request.GET.get("status", "")
    if site_filter:
        periods = periods.filter(site__name=site_filter)
    if status_filter:
        periods = periods.filter(status=status_filter)
    return render(
        request,
        "reduction/period_list.html",
        {
            "periods": periods[:200],
            "sites": Site.objects.all().order_by("name"),
            "statuses": ReductionPeriod.STATUS_CHOICES,
            "site_filter": site_filter,
            "status_filter": status_filter,
        },
    )


def _period_context(period: ReductionPeriod) -> dict:
    active_conflict = (
        ReductionPeriod.objects.filter(site=period.site, date=period.date, status__in=("QUEUED", "RUNNING"))
        .exclude(pk=period.pk)
        .exists()
    )
    return {
        "period": period,
        "can_start": period.status in ("PENDING", "FAILED", "CANCELLED") and not active_conflict,
        "can_stop": period.status == "RUNNING",
        "can_reset": period.status in ("QUEUED", "RUNNING"),
    }


def period_detail(request, pk: int):
    period = get_object_or_404(ReductionPeriod, pk=pk)
    return render(request, "reduction/period_detail.html", _period_context(period))


def _handle_period_action(request, pk: int, action_fn):
    period = get_object_or_404(ReductionPeriod, pk=pk)
    try:
        result = action_fn(period)
    except PeriodActionError as exc:
        ctx = _period_context(period)
        ctx["action_error"] = str(exc)
        return render(request, "reduction/period_detail.html", ctx, status=400)
    target_pk = result.pk if isinstance(result, ReductionPeriod) else period.pk
    return redirect("period_detail", pk=target_pk)


@require_POST
def period_start(request, pk: int):
    return _handle_period_action(request, pk, start_period)


@require_POST
def period_stop(request, pk: int):
    return _handle_period_action(request, pk, stop_period)


@require_POST
def period_reset(request, pk: int):
    return _handle_period_action(request, pk, reset_period)


@require_POST
def period_restart(request, pk: int):
    return _handle_period_action(request, pk, restart_period)
