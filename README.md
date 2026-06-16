# LifeLine AI

LifeLine AI is an emergency dispatch and ambulance coordination platform for
tracking incidents, ambulances, hospital capacity, and response analytics.

The repository currently contains two Python backends:

- A Flask web app at the repository root with HTML/CSS/JS dashboards.
- A newer FastAPI backend in `backend/` with REST APIs, websocket broadcasts,
  seed data, and typed schemas.

## Features

- Dispatcher dashboard with live map, incident queue, fleet status, hospital
  capacity, charts, and user administration.
- Driver, citizen, and hospital-facing views served by the Flask app.
- JWT authentication with role-aware endpoints for admins, dispatchers,
  drivers, hospitals, and citizens.
- AI-assisted severity classification and hospital recommendation logic.
- Ambulance assignment, reassignment, tracking history, lifecycle timestamps,
  notifications, audit logs, and analytics.
- Local SQLite defaults for quick development, with PostgreSQL-compatible
  database URLs supported by the FastAPI backend.

## Project Structure

```text
.
|-- app.py                    # Flask application factory and web entry point
|-- routes/                   # Flask API blueprints
|-- templates/                # Flask-rendered HTML pages
|-- static/                   # Dashboard CSS and browser JavaScript
|-- models.py                 # Flask SQLAlchemy models
|-- init_db.py                # Flask demo data initialization
|-- ai_engine.py              # Flask severity and hospital recommendation logic
|-- backend/
|   |-- app/main.py           # FastAPI application entry point
|   |-- app/api/              # FastAPI routers
|   |-- app/models.py         # SQLAlchemy models
|   |-- app/schemas.py        # Pydantic schemas
|   |-- app/seed.py           # Deterministic demo data seed script
|   `-- requirements.txt      # FastAPI dependencies
|-- requirements.txt          # Flask dependencies
|-- hospitals.csv             # Hospital seed data for the Flask app
`-- ambulance_routes.csv      # Demo route data
```

## Run the Flask App

Use this path when you want the included browser UI.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`.

The app creates `lifeline.db` and seeds demo hospitals, ambulances, users, and
incidents on startup. On a fresh database the UI may show a first-run setup
screen; complete it with a new admin account, then sign in.

Seeded demo users use non-secret usernames such as `admin`, `dispatcher`, and
`driver1` through `driver10`. Passwords are intentionally not documented in the
repository. Set `SEED_ADMIN_PASSWORD`, `SEED_DISPATCHER_PASSWORD`, and
`SEED_DRIVER_PASSWORD` in your private `.env` before the first run, or use the
generated local passwords printed in the startup logs.

Never commit `.env` or production credentials.

Useful pages:

- `http://localhost:5000/` - dispatcher dashboard
- `http://localhost:5000/driver` - driver mode
- `http://localhost:5000/citizen` - citizen mode
- `http://localhost:5000/hospital` - hospital mode

## Run the FastAPI Backend

Use this path when you want the API-first backend.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

Open:

- API health check: `http://localhost:8000/api/health`
- Swagger UI: `http://localhost:8000/docs`
- Websocket endpoint: `ws://localhost:8000/ws`

The FastAPI seed script creates demo accounts for admin, dispatcher, driver,
hospital, and citizen roles. Passwords come from your private `.env` values, or
are generated and printed locally during `python -m app.seed`.

Seeded demo identifiers:

| Role | Email or Username |
| --- | --- |
| Admin | `admin@lifeline.ai` |
| Dispatcher | `dispatcher@lifeline.ai` |
| Driver | `driver1@lifeline.ai` |
| Hospital | `hospital1@lifeline.ai` |
| Citizen | `citizen@lifeline.ai` |

## Environment Variables

Copy `.env.example` to `.env` for local development and fill in private values.
`.env` is ignored by git. The FastAPI backend can read either the repository
root `.env` or `backend/.env` when run from `backend/`.

Flask app:

```env
SECRET_KEY=
JWT_SECRET_KEY=
DATABASE_URL=sqlite:///lifeline.db
ORS_API_KEY=
SEED_ADMIN_PASSWORD=
SEED_DISPATCHER_PASSWORD=
SEED_DRIVER_PASSWORD=
```

FastAPI backend:

```env
DATABASE_URL=sqlite:///./lifeline.db
JWT_SECRET=
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
ORS_API_KEY=
SEED_ADMIN_EMAIL=admin@lifeline.ai
SEED_ADMIN_PASSWORD=
SEED_DISPATCHER_PASSWORD=
SEED_DRIVER_PASSWORD=
SEED_HOSPITAL_PASSWORD=
SEED_CITIZEN_PASSWORD=
CORS_ORIGINS=*
```

`ORS_API_KEY` is optional. When it is empty, routing logic falls back to
haversine-distance estimates so the app still works offline.

## API Overview

The Flask app exposes API routes under `http://localhost:5000/api`.

- `/api/auth` - setup, registration, login, logout, password reset, current user
- `/api/users` - admin user management
- `/api/ambulances` - fleet registration and driver assignment
- `/api/hospitals` - hospital listing and capacity updates
- `/api/incidents` - incident creation, assignment, status lifecycle
- `/api/tracking` - ambulance location updates and streaming data
- `/api/analytics` - dashboard summaries and heatmap data

The FastAPI backend exposes similar resources, plus dispatch, notifications,
admin audit, websocket updates, and richer tracking endpoints. See `/docs` for
the generated OpenAPI reference.

## Smoke Tests

The root-level `test_*.py` files are simple integration smoke scripts, not a
pytest suite. Run them against a disposable local database because they create
users, incidents, ambulances, and status transitions.

```powershell
python test_auth.py
python test_realism.py
python test_driver.py
```

Some scripts start or stop local servers directly and may need small shell
adjustments on Windows.

## Deployment Notes

- For the Flask UI, the start command should be `python app.py`.
- For the FastAPI backend, use `uvicorn app.main:app --host 0.0.0.0 --port %PORT%`
  from inside `backend/`, or the equivalent command for your host.
- Set strong secrets for `SECRET_KEY`, `JWT_SECRET_KEY`, and `JWT_SECRET` in
  production.
- Use a managed database URL for persistent deployments instead of the default
  local SQLite files.
