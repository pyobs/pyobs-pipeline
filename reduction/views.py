from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.shortcuts import redirect, render


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
