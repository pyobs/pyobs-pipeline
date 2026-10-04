# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries for releases before this file existed were generated from commit subjects.

## [2.2.2] - 2026-10-04

- Add MIT LICENSE
- docs: mark Keycloak login plan implemented/deployed, close #17

## [2.2.1] - 2026-09-13

- fix: sidebar username comment leaking into rendered output

## [2.2.0] - 2026-09-13

- feat: add Keycloak/OIDC login via pyobs-auth

## [2.1.1] - 2026-09-09

- feat: mark a period COMPLETED_WITH_ERRORS when Reduction reports frame/calib failures
- docs: fix stale pyobs-core dependency description in CLAUDE.md
- Address review nits: doc drift + rounding disagreement
- Support per-exptime dark masters: config + exptime in period UI
- Require stable pyobs-core>=2.0.0
- Remove cross-repo specs/ link from README
- Add UI screenshots to docs and README
- Add Dependabot auto-merge workflow for patch/minor updates
- Add .readthedocs.yml

## [2.1.0] - 2026-09-01

- docs: fix stale pyobs-core dependency description in CLAUDE.md
- Address review nits: doc drift + rounding disagreement
- Support per-exptime dark masters: config + exptime in period UI

## [2.0.0] - 2026-08-26

- Require stable pyobs-core>=2.0.0
- Remove cross-repo specs/ link from README
- Add UI screenshots to docs and README
- Add Dependabot auto-merge workflow for patch/minor updates
- Add .readthedocs.yml
- Add Sphinx docs from scratch
- Fix login 403 behind TLS-terminating proxy: support CSRF_TRUSTED_ORIGINS
- CI: run collectstatic before tests
- Fix ADMIN_PASSWORD_HASH escaping docs and guard against regression (#4)
- Add a distinct favicon and login icon
- Add configurable pyobs logo to sidebar header
- Add light/dark mode switcher and version display
- to 2.0.0.dev

## [0.3.0] - 2026-08-11

- Add whitenoise for static file serving in production
- Change pyobs-core pin from exact to lower bound

## [0.2.0] - 2026-08-10

- Add CI workflows: run tests, publish Docker image to GHCR on release
- Drop per-frame list from progress card, move progress bar below calibs
- Add live progress reporting to the reduction detail page, pin pyobs-core release
- Collapse dashboard recent periods and site cards to latest per site/date
- Collapse reduction periods list to latest per site/date, add history view
- Add Site.siteid, reject slashes in Site.name, flush logs live during a run
- Add CLAUDE.md
- Surface on_error for every step, move it + Save into the card header
- Hide the archive field in the pipeline step editor
- Pick up pyobs-core's archive-propagation fix, add regression test
- Discover all image processors dynamically instead of a curated list
- Replace SitePipeline I/O JSON textareas with structured form fields
- Add tests (Step 10)
- Add Dockerfile, Compose, and deploy docs (Step 9)
- Add dashboard (Step 8)
- Add log viewer auto-refresh (Step 7)
- Add ReductionPeriod management views (Step 6)
- Add Celery + Redis integration (Step 5)
- Add pipeline builder views (Step 4)
- Add site management views (Step 3)
- Scaffold Django project and reduction models
