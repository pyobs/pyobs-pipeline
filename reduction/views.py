from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.shortcuts import get_object_or_404, redirect, render

from reduction.forms import SiteForm, SitePipelineForm
from reduction.models import Site, SitePipeline


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
