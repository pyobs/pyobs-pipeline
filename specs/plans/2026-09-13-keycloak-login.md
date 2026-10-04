# Plan: Keycloak login for pyobs-pipeline

Tracks #17 ("Add Keycloak login"). Applies the already-decided, already-shipped design from
`pyobs-core`'s `specs/design/shared-auth-keycloak.md` and `shared-authz-keycloak.md` (ADRs 0011,
0014) to this repo — no new design work, this is a fourth cutover of a pattern already live in
pyobs-archive, pyobs-portal, and pyobs-web-admin (`v2.1.0` everywhere, see
`pyobs-core/specs/plans/2026-08-28-shared-authz-keycloak.md`). **pyobs-web-admin is the reference
implementation to copy**, not archive/portal — it's the only one of the three that's a plain
session-based Django app with a single hardcoded admin/password account sitting next to
Keycloak, the same shape pyobs-pipeline is in today. Archive/portal are DRF APIs with
`KeycloakAuthentication`; not relevant here.

Status: **implemented, released, and deployed (2026-09-13)**. Shipped in v2.2.0
(`5171b8e`/`2c01f0b`); a template bug found live in prod (multi-line `{# #}` comment leaking into
rendered HTML — Django's inline comment tag only strips single-line content) was fixed same-day in
v2.2.1 (`aebcf5a`/`2c4a1a6`). Deployed and verified live at MONET
(`pipeline.monet.uni-goettingen.de`) — GWDG one-click login and local-Keycloak-account fallback
both confirmed working end to end, `thusser` added to `/pyobs-pipeline`. Issue #17 closed.

Repos: pyobs-pipeline (this plan doesn't touch pyobs-auth or any other repo — no new library
work, just consuming what already exists).

## Decisions locked in for this plan (2026-09-13)

- **Supplement, not replace**: `ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH` stays as a break-glass
  fallback exactly like web-admin's, not removed. Rationale there (`pyobs_web_admin/settings.py:92-93`
  comment) applies unchanged: "kept working rather than removed, since it's the only way in if
  Keycloak itself is unreachable."
- **Login-only authorization gate**: a single `REQUIRED_GROUPS = ["/pyobs-pipeline"]`, no client
  role. Any member of that group can do everything a logged-in user can do today (start/stop/reset
  any site's periods) — this matches current behavior (no per-action permission check exists
  today; `reduction/views.py`'s `period_start`/`period_stop`/`period_reset` gate only on
  `LoginRequiredMiddleware`, not on who's logged in). A `pipeline-admin` client role can be added
  later the same way portal's `portal-admin` role was, without redesign.
- **Audit trail is a separate follow-up issue**, not part of this plan. Once real per-user
  Keycloak identities exist, recording `started_by`/`stopped_by`/`reset_by` (or a log line) on
  `ReductionPeriod` becomes possible for the first time — file that as a new issue once this
  lands, since today's single shared admin account makes an audit trail meaningless (everything
  would attribute to `"admin"`).

## Resolved: session engine (2026-09-13)

Switched `SESSION_ENGINE` to `db` (was `signed_cookies`), matching web-admin/portal. See
rationale below — kept for the record now that it's implemented.

**Session engine (former open question).** `pyobs_pipeline/settings.py:62` deliberately uses
`SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"` ("no session table needed" —
lets `web`/`worker`/`beat` share one sqlite file without a session table in the mix). But
`pyobs_auth.views.CallbackView` (`pyobs-auth/pyobs_auth/views.py:126-143`) **silently declines to
store the Keycloak refresh token** when `SESSION_ENGINE` is cookie-backed (a signed cookie isn't
encrypted, so it won't hand a bearer refresh credential to the browser) — it logs a warning and
moves on. Practical effect: `KeycloakSessionRefreshMiddleware` becomes a permanent no-op, and
revoking someone's `/pyobs-pipeline` group membership in Keycloak only takes effect at their next
login, bounded by `SESSION_COOKIE_AGE`, not within one access-token lifetime like web-admin gets.
Two ways forward:
1. **Keep `signed_cookies`, accept the weaker revocation bound.** No changes to the existing
   DB/session architecture. Reasonable given this is an institute-internal tool with a handful of
   users, but it's a real, deliberate gap versus every other pyobs-auth consumer — worth writing
   down rather than discovering by reading a warning log later.
2. **Switch to `django.contrib.sessions.backends.db`**, matching web-admin exactly. Needs a
   `django_session` table (via `django.contrib.sessions` in `INSTALLED_APPS` + migrate — cheap,
   same sqlite file, same WAL/busy-timeout settings already in place for the multi-process
   share). Gets the full revocation-within-one-token-lifetime property.

Recommendation: option 2 — the WAL-mode sqlite setup already tolerates concurrent web/worker/beat
access to one file, so a session table doesn't add new contention, and it keeps pipeline's
security posture consistent with the rest of the fleet rather than a documented exception. Confirm
before starting section 2 below.

## 0. Keycloak admin/deployment config (not pyobs code)

Done for MONET (2026-09-13), via `central/auth/create_client.sh` on `mc`
(`monet.uni-goettingen.de`) — see `pyobs-monet`'s own
`specs/topology/keycloak-service-topology.md` for the fleet-wide topology this fits into. Other
deployments (IAG-VT, etc.) repeat this section per-site when they get a pipeline instance.

- [x] Create realm group `/pyobs-pipeline` (mirrors `/pyobs-archive`; unlike `/pyobs-portal-*`/
      `/pyobs-web-admin-*`, no site suffix needed — pipeline is deployed centrally, one instance
      fleet-wide, same shape as archive, not per-site).
- [x] Register a new Keycloak client `pipeline` in the shared `pyobs` realm (confidential client,
      audience mapper + `groups` default scope wired by `create_client.sh`).
- [x] Set the client's redirect URI to
      `https://pipeline.monet.uni-goettingen.de/accounts/keycloak/callback/` and post-logout
      redirect URI to `https://pipeline.monet.uni-goettingen.de/`.
- [x] Set `IDP_HINT=gwdg`/`IDP_LABEL=GWDG` for the one-click GWDG login button, matching archive.
- [x] Assigned `thusser` to `/pyobs-pipeline`; confirmed via `kcadm get users/.../groups`.

## 1. Package + settings

- [x] `pyproject.toml`: add `"pyobs-auth>=2.1.0"` to `dependencies`.
- [x] `INSTALLED_APPS`: add `"django.contrib.contenttypes"`, `"django.contrib.auth"`,
      `"django.contrib.sessions"` (needed for `django.contrib.auth.models.User` and, if the
      session-engine question above resolves to option 2, the session table), `"pyobs_auth"`, and
      a new `"pyobs_pipeline.authentication"` app (see section 2). No `django.contrib.admin` needed
      — unlike web-admin, this plan's login-only gate mints active users directly (no local
      activation gate to administer), so there's no Django-admin-backed activation UI to add.
- [x] `MIDDLEWARE`: add `"django.contrib.auth.middleware.AuthenticationMiddleware"` (not present
      today — pipeline currently has no concept of `request.user`) before
      `"pyobs_auth.middleware.KeycloakSessionRefreshMiddleware"`, both before
      `"reduction.middleware.LoginRequiredMiddleware"`. Order per web-admin's
      `pyobs_web_admin/settings.py:23-38`.
- [x] New `PYOBS_AUTH` settings block, same shape as web-admin's
      (`pyobs_web_admin/settings.py:105-127`), values adapted:
      ```python
      PYOBS_AUTH = {
          "SERVER_URL": "",  # empty disables Keycloak entirely, login page shows password-only
          "REALM": "pyobs",
          "CLIENT_ID": "pipeline",
          "CLIENT_SECRET": "",
          "REDIRECT_URI": "",
          "POST_LOGOUT_REDIRECT_URI": "",
          "IDP_HINT": "",
          "IDP_LABEL": "",
          "USER_RESOLVER": "pyobs_pipeline.authentication.keycloak.resolve_user",
          "REQUIRED_GROUPS": ["/pyobs-pipeline"],
          "ENFORCE_LOCAL_ACTIVE": False,  # login-only gate decision above; no local activation surface
      }
      ```
- [x] Wire the same env-var-over-default pattern the rest of `settings.py` already uses (lines
      97-103) for `PYOBS_AUTH`'s `SERVER_URL`/`CLIENT_ID`/`CLIENT_SECRET`/`REDIRECT_URI`/
      `POST_LOGOUT_REDIRECT_URI`, e.g. `KEYCLOAK_SERVER_URL`, `KEYCLOAK_CLIENT_SECRET`, etc., so
      Docker Compose deployments configure it the same way `ADMIN_USERNAME` already is.
- [x] `docker-compose.yml`: added the new `KEYCLOAK_*` env vars to all three services'
      (`web`/`worker`/`beat`) `environment:` lists, alongside `ADMIN_USERNAME`/
      `ADMIN_PASSWORD_HASH` (matches how existing vars are already passed to all three, not just
      `web`). Also documented in `.env.example` and `docs/source/configuration.rst`.
- [x] If the session-engine question resolves to option 2: change `SESSION_ENGINE` to
      `"django.contrib.sessions.backends.db"` and run a migration to create `django_session`.

## 2. `pyobs_pipeline.authentication` app

New minimal app, mirroring `pyobs_web_admin.authentication` (not portal's, which adds the
`is_superuser`-from-role sync this plan's login-only gate doesn't need):

- [x] `models.py`: `KeycloakIdentity` — copy of
      `pyobs-web-admin/pyobs_web_admin/authentication/models.py` verbatim (`user` OneToOne +
      `keycloak_sub` unique `CharField`). Migration.
- [x] `keycloak.py`: `resolve_user(claims)` — copy of
      `pyobs-web-admin/pyobs_web_admin/authentication/keycloak.py`'s `resolve_user` verbatim
      (sub-first lookup, then email, then username fallback, mint `is_active=True` on miss). No
      role-sync needed (login-only gate).
- [x] `admin_sync.py` (optional but recommended for consistency): copy web-admin's
      `sync_admin_user` post_migrate signal so `ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH` becomes a
      real `django.contrib.auth` superuser at migrate time, the same way `login_view` will need it
      (see section 3) — keeps the sync in one place instead of duplicated inline in the view.

## 3. Views, urls, middleware

- [x] `pyobs_pipeline/urls.py`: add `path("accounts/keycloak/", include("pyobs_auth.urls"))`.
- [x] `reduction/views.py`'s `login_view` (currently `views.py:19-37`): on successful
      admin/password check, also call `django.contrib.auth.login()` with a real `User` (
      `get_or_create`d from `ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH`, matching web-admin's
      `modules/views.py:26-46` pattern), not just the `session["authenticated"]` flag — so both
      login paths converge on `request.user` and `LoginRequiredMiddleware` only needs one check.
- [x] `reduction/middleware.py`'s `LoginRequiredMiddleware` (currently gates on
      `request.session.get("authenticated")` only, exempting just `/login/` —
      `reduction/middleware.py:4-11`): extend the condition to
      `request.session.get("authenticated") or request.user.is_authenticated`, and exempt
      `/accounts/keycloak/` alongside the existing `/login/` exemption, matching web-admin's
      `modules/middleware.py:34-59`.
- [x] `logout_view`: added `django.contrib.auth.logout()`. Kept the bespoke view rather than
      routing through `pyobs_auth`'s `LogoutView` — matches web-admin's actual shipped `/logout/`
      route, which also doesn't do RP-Initiated Logout. Revisit only if a real "still logged into
      Keycloak after pipeline logout" complaint shows up.

## 4. Templates

- [x] `templates/base.html`: the sidebar sign-out button showed `{{ request.session.username }}`,
      which the admin/password `login_view` sets but a Keycloak login never does — a
      Keycloak-authenticated user would have seen a blank name. Fixed with a
      `|default:request.user.get_username` fallback (not caught by the plan when it was written;
      found while implementing).
- [x] `templates/registration/login.html`: add a "Log in with Keycloak" button/link to
      `pyobs_auth`'s `LoginView` (`/accounts/keycloak/login/`), shown only when
      `PYOBS_AUTH['SERVER_URL']` is set (a context processor or template flag needs to expose
      that — web-admin does this via `modules/context_processors.py`, check how it conditions the
      button there before duplicating the approach).

## 5. Tests

- [x] `pyobs_pipeline/authentication/tests.py`: `resolve_user` unit tests (sub match, email
      fallback, username fallback, mint-new, mint-active), verbatim port of `pyobs-web-admin`'s
      `authentication/tests.py`. Existing `reduction/tests/test_views.py` admin/password login
      tests re-run unchanged (86 tests total, all green) — no separate Keycloak-URL-exemption
      test added, since there's no Keycloak server in CI to actually hit those views against; the
      exemption itself is a one-line `startswith` check.
      `.github/workflows/tests.yml` updated to run both `reduction` and
      `pyobs_pipeline.authentication`.

## Not in this plan

- Per-action authorization (a `pipeline-admin` role gating `can_start`/`can_stop`/`can_reset`) —
  explicit "login-only gate" decision above; revisit if/when pipeline gets more than one class of
  user.
- Audit trail (`started_by`/`stopped_by`/`reset_by` on `ReductionPeriod`) — separate follow-up
  issue, meaningless until real per-user identities exist via this plan.
- `ENFORCE_LOCAL_ACTIVE` / local per-user activation UI — not needed under the login-only gate;
  `REQUIRED_GROUPS` is the whole authorization decision.
- Any change to `pyobs-auth` itself — this plan only consumes the existing `v2.1.0` API.
