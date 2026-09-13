from django.shortcuts import redirect


class LoginRequiredMiddleware:
    """Two independent logins share this gate: the shared admin/password account (a plain
    session["authenticated"] flag - also, since reduction.views.login_view, a real
    django.contrib.auth login) and Keycloak (a real django.contrib.auth User, via request.user -
    AuthenticationMiddleware must run before this)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        authenticated = request.session.get("authenticated") or request.user.is_authenticated
        if not authenticated:
            exempt = request.path_info.startswith("/login/") or request.path_info.startswith(
                "/accounts/keycloak/"
            )
            if not exempt:
                return redirect(f"/login/?next={request.path_info}")
        return self.get_response(request)
