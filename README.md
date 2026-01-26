# Smart Ambulance Tracker

Real-time ambulance tracking and nearest-hospital routing dashboard built with Dash/Plotly and a Flask GPS ingest server.

## Features
- Live GPS ingest via simple mobile web page (Flask) storing to `live_positions.csv`.
- Dash map dashboard with Live and Simulation modes.
- Nearest-hospital routing using OpenRouteService (ORS) directions API.
- Hospital directory (50 hospitals) and sample ambulance routes for simulation.
- Supports multiple ambulances (ID field on sender page).
- Map preserves zoom/pan while updating; auto-fits routes when needed.

## Quick Start (Local)
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set your ORS API key (get one free at https://openrouteservice.org):
   ```bash
   set ORS_API_KEY=YOUR_KEY_HERE   # PowerShell: $env:ORS_API_KEY="YOUR_KEY_HERE"
   ```
3. Run the tracker server (GPS ingest):
   ```bash
   python tracker_server.py
   ```
   - Open the printed URL (or http://localhost:5000) on a phone/laptop.
   - Allow location; enter ambulance ID if needed; it starts sending live GPS.
4. Run the dashboard:
   ```bash
   python app.py
   ```
   - Open the shown Dash URL (default http://127.0.0.1:8050).
   - Choose **Live GPS** to see real ambulances, or **Simulation** for demo.

## Stable Public URL Options
- **LocalTunnel (custom subdomain):**
  ```bash
  lt --port 5000 --subdomain myambulance
  # use https://myambulance.loca.lt on phones
  ```
- **Railway/Render deploy (Student Pack friendly):**
  - `Procfile` included. Set env var `PORT` is handled automatically; set `ORS_API_KEY` in project settings.
  - Start command: `python tracker_server.py` (or `gunicorn tracker_server:app` if you add gunicorn).

## Files
- `app.py` — Dash dashboard (map, routing, live/sim modes).
- `tracker_server.py` — Flask server for GPS ingest + sender web page.
- `utils.py` — haversine distance, interpolation helpers.
- `hospitals.csv` — 50 hospitals with lat/lon.
- `ambulance_routes.csv` — sample simulated routes (A–O).
- `live_positions.csv` — current positions store (auto-created).
- `requirements.txt` — Python deps.
- `Procfile` — process definition for hosting.

## API Endpoints (tracker_server)
- `POST /update_location` — body: `{ id, lat, lon, speed_kmph? }` writes to CSV.
- `GET /positions` — returns JSON list of current rows.
- `GET /` — GPS sender page (mobile-friendly).

## Notes
- Keep your ORS API key private; prefer env vars over hardcoding.
- If map tiles don’t load, check internet/connectivity or switch map style.
- For multiple ambulances, use distinct IDs in the sender page.

## Troubleshooting
- **Map keeps resetting zoom:** fixed via `uirevision`; ensure you’re on latest code.
- **No live points:** verify phone has location permission and correct URL (localtunnel/hosted URL).
- **Routing fails:** check ORS API key or network; console logs show API errors.
