# Adaptive Procurement Scheduling

Adaptive procurement scheduling and real-time queue management platform for
reducing farmer waiting time and uncertainty at agricultural procurement
centres. The repository contains a FastAPI backend, a React/Vite frontend,
PostgreSQL migrations, deterministic demo fixtures, and an explainable
scheduling/insights layer.

## What the application does

- Lets farmers register, browse active procurement centres and available
  slots, create bookings, check in, and track queue/ETA state.
- Gives centre staff a centre-scoped operations dashboard for live queue
  actions, throughput, booking assessments, and procurement insights.
- Gives administrators global access to centre operations, user provisioning,
  and throughput recalculation.
- Classifies bookings as `ON_TRACK`, `AT_RISK`, or `DELAYED` using live queue
  depth, measured service throughput, and the booking slot window.
- Provides explainable recommendations such as `KEEP_SLOT`, `WARN_FARMER`,
  `PROPOSE_NEW_SLOT`, and `RECOMMEND_ALTERNATE_CENTRE`.
- Keeps external agricultural reference data separate from operational
  scheduling inputs. Reference facts enrich centre views but never alter
  queue ordering, ETA, throughput, or scheduling decisions.

## Project foundation (Phase 1)

- Backend: FastAPI modular monolith scaffold in `backend/app/`
- Frontend: React + Vite scaffold in `frontend/`
- Configuration templates: `backend/.env.example` and `frontend/.env.example`
- Database migrations: `backend/alembic/`
- Automated backend tests: `backend/tests/`

## Architecture

```text
React/Vite frontend
  farmer portal + staff operations portal
             |
             | JSON API + JWT bearer token
             v
FastAPI application
  routers -> services -> repositories -> SQLAlchemy models
             |
             +--> PostgreSQL (operational and reference data)
             +--> manual CSV reference-data import (CLI only)
```

The frontend uses a small hash-based router and stores the farmer profile and
JWT session in browser `localStorage`. Live farmer and staff views poll the
API; the application does not currently use WebSockets. The backend is a
single deployable service and exposes OpenAPI documentation at `/docs` and
`/redoc` when it is running.

### Main source areas

| Area | Purpose |
| --- | --- |
| `backend/app/api/routers/` | HTTP endpoints and authorization boundaries |
| `backend/app/services/` | Booking, queue, ETA, throughput, scheduling, and insight logic |
| `backend/app/repositories/` | Database access |
| `backend/app/models/` and `backend/app/schemas/` | SQLAlchemy persistence models and Pydantic API contracts |
| `backend/app/db/seed.py` | Idempotent local demo data and demo users |
| `backend/app/db/scenarios.py` | Dev-only scheduling state transitions |
| `backend/app/db/import_reference_data.py` | Provenance-aware offline CSV importer |
| `frontend/src/screens/` | Farmer and staff workflows |
| `frontend/src/core/` | Routing, auth/session storage, API-facing state, and scheduling adapters |
| `frontend/src/components/` | Shared UI and staff dashboard components |

## Authentication & authorization (Phase 4 - production hardening)

The API requires JWT bearer authentication for every endpoint that
touches a specific farmer's, centre's, or admin-only data. Three roles
exist: `FARMER`, `CENTRE_STAFF` (scoped to exactly one procurement
centre), and `ADMIN`.

- `POST /api/auth/register` - public, unauthenticated self-registration
  for `FARMER` only (requires an existing `farmer_id` from
  `POST /api/farmers/`). `CENTRE_STAFF` and `ADMIN` cannot be
  self-registered through this endpoint - both are privileged roles and
  must be provisioned by an existing `ADMIN` via `POST /api/admin/users`
  instead.
- `POST /api/auth/login` - OAuth2 password flow (`username` = email);
  returns a bearer access token.
- `GET /api/auth/me` - current authenticated user.

Remaining endpoints stay public where the data is non-sensitive
(browsing centres/slots, creating a farmer profile). Booking, queue,
scheduling, and admin/throughput endpoints enforce ownership/centre-
scope/role checks server-side - see `backend/app/api/deps.py` for the
shared dependencies and `backend/tests/test_security.py` for the
behavioral test coverage.

The frontend in `frontend/` implements the full auth flow: the
onboarding screen creates a farmer profile and its linked `FARMER`
account (or logs an existing farmer back in), and the centre-dashboard
route (`#/staff`) is gated behind a `CENTRE_STAFF`/`ADMIN` login. See
"Demo login accounts" below for out-of-the-box staff/admin credentials.

### Notification intents (Phase 4A)

Persisted `SchedulingDecision` snapshots can produce provider-neutral
`NotificationIntent` records for farmer-facing adaptive outcomes. Intents are
read/audit records with an initial `PENDING` state; Phase 4A does not send
SMS, WhatsApp, IVR, or in-app messages. A future delivery adapter will consume
the flow:

```text
SchedulingDecision -> NotificationIntent -> delivery adapter
```

## Local setup

**Prerequisites:** Python 3.12+, Node 20+, and a PostgreSQL database (a
local Postgres via Docker/`brew services`/etc, or any hosted instance).

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then fill in DATABASE_URL, JWT_SECRET_KEY, etc.
alembic upgrade head            # run migrations
python -m app.db.seed           # optional: seed demo centres/farmers/bookings + demo logins
uvicorn app.main:app --reload   # http://127.0.0.1:8000
```

`GET /health` reports whether the configured database is reachable -
useful for confirming your `.env` is correct before starting the
frontend.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env             # VITE_API_BASE_URL should point at the backend above
npm run dev                      # http://127.0.0.1:5173
```

### Tests

```bash
cd backend
pytest                           # full suite
pytest tests/test_security.py -v # auth/RBAC-focused suite
```

```bash
cd frontend
npm run lint
npm run build
```

### Demo login accounts

Running `python -m app.db.seed` seeds two procurement centres, five
farmers, sample bookings/queue state, and the following login accounts
(printed to stdout by the seed script itself):

| Role           | Email                          | Password         |
| -------------- | ------------------------------- | ---------------- |
| `ADMIN`        | `admin@demo.test`               | `AdminDemo123!`   |
| `CENTRE_STAFF` | `staff.thanjavur@demo.test`     | `StaffDemo123!`   |
| `CENTRE_STAFF` | `staff.kumbakonam@demo.test`    | `StaffDemo123!`   |

There is deliberately no seeded farmer login - sign up as a new farmer
through the onboarding screen to exercise the real registration flow
end-to-end. These are demo-only credentials for a locally seeded
database; never reuse them in a real deployment.

## API overview

All application resources are under `/api`. Use the generated OpenAPI
documentation (`http://127.0.0.1:8000/docs`) for request and response
schemas.

| Resource | Endpoints | Access |
| --- | --- | --- |
| System | `GET /api/test`, `GET /health`, `GET /` | Public |
| Authentication | `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` | Register is public for farmers; login is public; `me` requires a bearer token |
| Farmers | `POST /api/farmers/`, `GET /api/farmers/{farmer_id}` | Create is public; lookup is owner/admin scoped |
| Centres and slots | `GET /api/centres/`, `GET /api/centres/{centre_id}/slots`, `GET /api/slots/{slot_id}` | Public |
| Bookings | `POST /api/bookings/`, `GET /api/bookings/{booking_id}` | Authenticated; farmer ownership/admin rules apply |
| Queue and ETA | `POST /api/queue/check-in`, queue lookup/actions, `GET /api/queue/{queue_entry_id}/eta` | Farmer ownership or centre-staff/admin scope |
| Scheduling | `GET /api/scheduling/bookings/{booking_id}`, `GET /api/scheduling/centres/{centre_id}` | Booking owner or centre-staff/admin scope |
| Centre context | `GET /api/centres/{centre_id}/reference-context` | Public, read-only context |
| Centre insights | `GET /api/centres/{centre_id}/procurement-insights` | Centre staff for their centre or admin |
| Reference data | `GET /api/reference/`, `GET /api/reference/{reference_id}` | Authenticated read-only access |
| Administration | `POST /api/admin/users`, throughput read/recalculate endpoints | Admin, with centre scoping for staff reads |

Queue actions are `call-next`, `start-serving`, `complete`, and `no-show`.
Notifications currently expose only a foundation placeholder endpoint; no
external SMS, IVR, or push provider is integrated.

## Running the adaptive scheduling demo

After migrations and seeding, run the scenario fixture from `backend/`:

```bash
python -m app.db.scenarios normal
python -m app.db.scenarios at_risk
python -m app.db.scenarios delayed
python -m app.db.scenarios delayed_alt_centre
python -m app.db.scenarios status
python -m app.db.scenarios reset
```

Each command prints the relevant booking and centre IDs and the API URL to
poll. The fixture is development-only, refuses to run with
`APP_ENV=production`, and only changes rows belonging to its dedicated demo
fixture.

### Phase 1 deterministic adaptive simulation

Centre staff and admins can run the isolated simulation through
`POST /api/simulation/runs` with a `centre_id`. It uses synthetic in-memory
state and never creates or changes bookings, queue entries, or throughput
rows. A fixed `seed` reproduces the same event sequence and decision trace.
Runs are centre-owned: staff can only read runs for their assigned centre,
while admins can read any centre. The focused
`GET /api/simulation/runs/{run_id}/metrics` and
`GET /api/simulation/runs/{run_id}/trace` endpoints expose the corresponding
parts of the full response.

The event-driven response separates true state from the latest timestamped
(optionally delayed) observation and includes the five processing stages, stage-specific resources,
resource outages/recovery, queue work, service time, quantities, centre status,
completed work, observation age, a richer completion interval, and
baseline/adaptive metrics. The trace records `OBSERVE -> ESTIMATE -> ASSESS ->
ADAPT` decisions. High uncertainty is reported as an interval rather than an
exact ETA.

The staff dashboard's **Adaptive simulation** panel lets staff vary the seed,
horizon, and observation delay. These values are controlled synthetic
assumptions, not ML predictions or real centre telemetry.

## Data provenance: reference/external agricultural data

The scheduling engine (queue, throughput, ETA, ON_TRACK/AT_RISK/DELAYED)
runs entirely on real, application-generated operational data - actual
bookings, check-ins, and served timestamps. It does not use, and is not
affected by, anything described in this section.

Separately, the `reference_datasets` table holds external/official
statistical context (e.g. district/season agricultural statistics,
AGMARKNET-style market price observations). Every row is tagged with a
`data_status`:

| `data_status` | Meaning |
| --- | --- |
| `REAL`       | Imported from an actual official source. `source`, `source_reference`, and `retrieved_at` are always populated. |
| `DERIVED`    | Computed from REAL rows (not used yet - reserved for future calibration work). |
| `SIMULATED`  | Synthetic data for load/stress testing. |
| `DEMO`       | Placeholder data for demos/walkthroughs. |

**This table currently contains no real government/farmer/DPC data.**
There is no verified real-time TNCSC DPC procurement API and no verified
public farmer-level DPC operational dataset this project can legitimately
claim to have integrated. The AGMARKNET/data.gov.in market-price data and
the Tamil Nadu Season & Crop Report are the identified candidate REAL
sources; importing an actual REAL dataset is a manual, separate step
(see below) - nothing in this codebase invents or assumes such data.

### Reading reference data

`GET /api/reference/` (any authenticated user) lists rows, filterable by
`district`, `dataset_type`, and `metric_name`. `GET /api/reference/{id}`
fetches a single row. There is no `POST`/`PUT`/`DELETE` for this
resource - reference data can only enter the system through the import
procedure below, never through an arbitrary API request.

### Importing reference data (manual CSV import)

```bash
cd backend
python -m app.db.import_reference_data <csv_path> \
    --data-status REAL \
    --source "Tamil Nadu Season and Crop Report 2024-25" \
    --source-reference "https://<official-source-url-or-document-id>" \
    --retrieved-at 2026-09-01
```

The CSV must have a header row with exactly these columns:
`dataset_type, district, season_or_period, metric_name, metric_value, unit`.
`data_status`, `source`, `source_reference`, and `retrieved_at` are
supplied once as command-line flags for the whole file, not read from the
CSV - a CSV is never assumed to be "automatically official" just because
it parses. Importing with `--data-status REAL` fails immediately, before
anything is written, unless `--source`, `--source-reference`, and
`--retrieved-at` are all supplied.

**Validation is all-or-nothing:** if any row in the CSV fails validation
(missing column, non-numeric `metric_value`, etc.), the entire import is
rejected and every problem found is printed - nothing is written. A
malformed value is never silently coerced to a default. A completely
blank row (e.g. a trailing spacer line some spreadsheet exports add) is
tolerated and skipped; a row with only *some* fields blank is still
treated as malformed and fails the batch.

**Idempotency:** a row already in the table with the same
`(dataset_type, district, season_or_period, metric_name, source)` is
skipped, not re-inserted or overwritten. Re-running the same import
command is therefore always safe. Importing a corrected figure for the
same fact requires a new `--source`/`--source-reference` (a new
provenance trail), not a silent overwrite of a previously-imported value.

### Not yet built (by design, for this milestone)

- No live AGMARKNET (or any) external API integration - only manual CSV
  import. A live-fetch integration (`app/integrations/`) is a deliberately
  separate, later milestone, gated on an optional API-key env var so its
  absence never breaks the app.

## Procurement/scheduling integration with reference data (Milestone 2)

Reference data is now consumed by the operational side of the app, but
only as read-only context - not as an input to any scheduling decision.

**Endpoint:** `GET /api/centres/{centre_id}/reference-context` (public,
matching this router's existing centre/slot listing endpoints) returns
the reference facts available for that centre's district, optionally
filtered by `dataset_type`, `metric_name`, and `season_or_period`. A
centre whose district has no matching reference data returns
`reference_facts: []` - a normal, expected result, not an error. Only a
genuinely unknown `centre_id` returns 404.

**Why district-only matching:** `ProcurementCentre.district` is the only
field the operational schema and `reference_datasets` genuinely share.
There is no `season_or_period` or controlled crop vocabulary anywhere in
the operational schema, and `Booking.crop_type` is free text - so this
integration does not attempt to auto-match a booking's crop to a
reference `metric_name`; that would be a fabricated heuristic, not a fact
drawn from the data. `season_or_period`/`dataset_type`/`metric_name` are
available as explicit, caller-supplied filters instead.

**Why no derived score/signal:** the one real dataset available at this
milestone - district paddy area, in lakh hectares - has no defensible
deterministic relationship to queue wait time or scheduling status.
Rather than invent a threshold or scoring formula to make the integration
look more sophisticated, Milestone 2 is a context/enrichment layer only.

**Architecture:**

```
reference repository (app/repositories/reference.py)
        v
reference service (app/services/reference_data.py - find_reference_context)
        v
procurement/scheduling integration (app/services/procurement_context.py)
        v
API (app/api/routers/centres.py)
```

`app/services/scheduling.py`, `eta.py`, `throughput.py`, `queue.py`, and
`bookings.py` are unmodified and do not import the reference-data layer
at all - so a reference-data problem (missing table, bad row, unexpected
query error) cannot structurally affect a scheduling/ETA/queue/booking
decision. This is enforced by a test that inspects those modules' source
for any reference-layer import, not just documented.

No new database migration was needed - this milestone only reads
existing `reference_datasets` rows at request time.

## Procurement insights (Milestone 3)

`GET /api/centres/{centre_id}/procurement-insights` provides an authenticated
centre-staff/admin view of the current operational state. It aggregates the
existing queue, booking, throughput, ETA, and scheduling services into typed
metrics, the existing `ON_TRACK`/`AT_RISK`/`DELAYED` status semantics, and
structured attention items with operational evidence. The response also
includes the centre's district reference facts, preserving their
`data_status`, source, source reference, and retrieval timestamp.

Reference facts are contextual only: they are never used to change queue
ordering, ETA, throughput, or scheduling decisions. A valid centre with no
matching reference rows still returns the operational insight with an empty
`reference_context` list. Optional `dataset_type`, `metric_name`, and
`season_or_period` query parameters apply the same explicit filters as the
reference-context endpoint.

The response also includes deterministic `recommendations`. Each recommendation
has a stable code, title, explanation, supporting operational evidence,
severity, and priority. Recommendations are derived only from the existing
scheduling status, queue state, and throughput availability; they do not
execute an operational action or change the authoritative scheduling engine.

## Deployment

The intended architecture is frontend on Vercel, backend on Render, and
a hosted PostgreSQL instance (Render/Supabase/Neon/etc).

**Backend (Render, or any container/PaaS host):**
- Start command: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Required env vars: `DATABASE_URL`, `JWT_SECRET_KEY` (a strong random
  value - the app refuses to start with the placeholder default once
  `APP_ENV=production`), `BACKEND_CORS_ORIGINS` (your deployed frontend
  origin), `APP_ENV=production`.
- Health check path: `/health`.

**Frontend (Vercel, or any static host):**
- Build command: `npm run build`; output directory: `dist`.
- Required env var: `VITE_API_BASE_URL` pointing at the deployed backend.

**Database:** run `alembic upgrade head` against the hosted instance
(the backend start command above does this automatically on deploy).
Seeding demo data (`python -m app.db.seed`) is optional and safe to skip
in a real deployment.
