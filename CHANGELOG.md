# Changelog

All notable changes to this project. Versions follow [semantic versioning](https://semver.org/).

## 1.0.0 — 2026-10-26

### Added
- `pyproject.toml` with a `sancscreen` console command, and pinned `requirements.lock` /
  `requirements-dev.lock` (generated with `uv pip compile --universal`).
- Container image: slim Python 3.12 base, non-root user, health check on `/healthz`.
- CI on every push: ruff, bandit, pip-audit, pytest with a coverage report.
- Settings from `SANCSCREEN_*` environment variables, checked at startup.
  `SANCSCREEN_ENV=production` refuses to start without hashed API keys, a database and
  `SANCSCREEN_SDN_XML` (OFAC's list; the built-in list is a demo). With a real list the toy
  ownership graph is not loaded.
- Per-client API keys with roles (`screener`, `viewer`, `analyst`, `monitor`, `admin`), stored as
  `sha256:<hex>`; `python -m sancscreen.ops keygen` makes new ones. Replaces the single
  `SANCSCREEN_API_KEY`.
- Screening log: every `/screen` result is stored with the caller, the list version
  (`sha256:` of the SDN file) and the full response. Hits start `open`; analysts mark them
  `cleared` (false positive) or `confirmed` with a note (`GET /screenings`,
  `GET /screenings/{id}`, `POST /screenings/{id}/review`). SQLite by default, Postgres through
  `SANCSCREEN_DATABASE_URL`; numbered migrations, `python -m sancscreen migrate`.
- Per-client rate limit, body cap (also for chunked bodies), security headers, validation errors
  that don't echo input; JSON logs with request IDs; `/healthz`, `/readyz` (database and
  watchlist) and Prometheus `/metrics` (`sancscreen_decisions_total` by decision and review).
- `SECURITY.md`, `docs/threat-model.md`, `docs/runbook.md`, `docs/model-card.md`.

### Changed
- OFAC's XML is parsed with `defusedxml` (no entity expansion or external fetches).
- `GET /watchlist` returns a page (`offset`, `limit` up to 1,000) instead of the whole list, which
  is 19,471 entries with a real list.
- `/health` is replaced by `/healthz` and `/readyz`; a 404 from `/ubo/check` no longer echoes the
  entity name; `/` serves a short banner (there was never a console file in this repository).
- A duplicate `pjsc` in the company-form set was removed (no effect: it is a set).

### Unchanged
- Transliteration, matching, thresholds, the ownership rules, and every benchmark, real-data and
  held-out number in the README and `results/`.
