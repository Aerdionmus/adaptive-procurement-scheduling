# adaptive-procurement-scheduling
Adaptive procurement scheduling and real-time queue management platform designed to reduce farmer waiting time and uncertainty at procurement centres.

## Project foundation (Phase 1)

- Backend: FastAPI modular monolith scaffold in `backend/app/`
- Frontend: React + Vite scaffold in `frontend/`
- Configuration template: `.env.example`

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
