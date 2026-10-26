# Runbook

How to deploy, configure and operate the screening service. Commands assume the repository root.

## Deploy

```bash
docker build -t sanctions-fuzzy-screening:1.0.0 .
python -m sancscreen.ops keygen              # one key per payment system, analyst and monitor
# SDN.XML: OFAC's XML export from sanctionslistservice.ofac.treas.gov
docker run -d --name sancscreen -p 8016:8016 -v sancscreen-data:/data \
  -v /srv/lists/SDN.XML:/lists/SDN.XML:ro -e SANCSCREEN_SDN_XML=/lists/SDN.XML \
  -e SANCSCREEN_KEYS_FILE=/run/secrets/sancscreen-keys.json \
  sanctions-fuzzy-screening:1.0.0
curl -fsS http://127.0.0.1:8016/readyz
```

The image runs in production mode as a non-root user with its SQLite database in `/data`. It
refuses to start, and logs why, without keys, a database or the SDN file. Loading the real list
takes a few seconds. Terminate TLS in front of it. For several replicas use Postgres
(`SANCSCREEN_DATABASE_URL=postgresql://...`) and give every replica the same list file.

Without Docker: `pip install -r requirements.lock && pip install -e .`, then `sancscreen serve`.

## Configure

| Variable | Required in production | Meaning |
|---|---|---|
| `SANCSCREEN_ENV` | — | `development` (default) or `production` |
| `SANCSCREEN_API_KEYS` / `SANCSCREEN_KEYS_FILE` | yes | JSON `{"sha256:<hex>": {"user": "...", "role": "..."}}`. Roles: `screener` (`/screen`, `/ubo/check`), `viewer` (read the log, watchlist, bench), `analyst` (screen, read, review), `monitor` (`/metrics`), `admin` |
| `SANCSCREEN_SDN_XML` | yes | path to OFAC's SDN.XML |
| `SANCSCREEN_DATABASE_URL` | yes | `sqlite:////data/sancscreen.db` or `postgresql://...` (development default: in memory) |
| `SANCSCREEN_HOST`, `SANCSCREEN_PORT` | — | default `127.0.0.1:8016`; a non-loopback address needs API keys |
| `SANCSCREEN_RATE_LIMIT` | — | requests per minute per client (default 120; raise it for a payment hub's key) |
| `SANCSCREEN_MAX_BODY_BYTES` | — | default 64,000 |
| `SANCSCREEN_CORS_ORIGINS` | — | origins allowed to call from a browser; none by default |
| `SANCSCREEN_LOG_LEVEL` | — | default `INFO` |

## Update the list

OFAC publishes changes several times a week, sometimes daily. At least once a day: download the
new SDN.XML, put it in place of the old file, restart the service (or roll the replicas), and check
that `/readyz` is ready and the `list_version` on a test screening changed. Keep each file you used:
the `list_version` on a logged result is the first 16 hex digits of its SHA-256.

## Watch

- `GET /healthz`: process up. `GET /readyz`: database answers and the watchlist is loaded.
- `GET /metrics` (role `monitor`): `http_requests_total`, `http_request_duration_seconds`,
  `errors_total`, `sancscreen_decisions_total{decision="BLOCK|REVIEW|REVIEW_EDD_25|CLEAR|review_*"}`.
- Logs: JSON lines with `request_id` (also in `X-Request-ID`); the startup line gives the list size
  and version.

Suggested alerts: `/readyz` failing; p95 `/screen` latency above 500 ms; the BLOCK or REVIEW share
moving sharply after a list update (a loader problem or a big designation round: look before
acting); open hits older than your review SLA (`GET /screenings?status=open`); a list file older
than a day.

## Rotate keys

API keys are the only secrets. Add the new hash to the key file and restart, give the client the
new key, then remove the old hash and restart. Remove a hash and restart to revoke at once.

## Back up and restore

SQLite (in the `/data` volume):

```bash
docker exec sancscreen python -c "import sqlite3; s=sqlite3.connect('/data/sancscreen.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d)"
docker cp sancscreen:/data/backup.db ./sancscreen-$(date +%F).db
```

Restore: stop the container, put the backup at `/data/sancscreen.db`, start it, check `/readyz`
and `GET /screenings`. Postgres: `pg_dump` / `pg_restore`; migrations run on start or with
`python -m sancscreen migrate`. Keep backups and the list files they refer to for your record-keeping
period (screening evidence), and restrict access: they hold customer names.

## Incidents

1. **A listed party was cleared or not flagged.** Find the screening by `query_id`
   (`GET /screenings` or the database), note its `list_version` and score, and follow the
   bank's sanctions-breach procedure (freeze, report). Add the variant to the tests and fix the
   matcher in a reviewed release; re-run the held-out set and report the numbers honestly.
2. **Service down.** Payments that need screening must queue or stop, never pass unscreened.
   Restart; if the list file is the cause, roll back to the previous file.
3. **Leaked API key.** Remove its hash and restart; review that user's screenings and reviews.
4. **Wrong list loaded.** Compare `list_version` with the file you meant to deploy; re-screen the
   payments screened in between against the right list.
