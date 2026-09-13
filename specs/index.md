# specs/

- [plans/](plans/index.md) — implementation plans, checklist-style; a plan moves/folds into
  `design/` once it ships (no `design/` yet — nothing here has needed one so far).

These are `pyobs-pipeline`-local docs. `pyobs-core` is the reference for the full `specs/`
convention across the `pyobs` ecosystem (it additionally has `adrs/` and `steering/`, and its own
`CLAUDE.md` explains when a doc belongs there instead of here — e.g. anything that also concerns
another sibling repo). See `pyobs-core`'s `specs/` for cross-repo design docs, plans, and ADRs that
happen to touch this repo — e.g. `../../pyobs-core/specs/design/shared-auth-keycloak.md` and
`../../pyobs-core/specs/design/shared-authz-keycloak.md` (the shared Keycloak/`pyobs-auth` design
this repo's own login plan applies).
