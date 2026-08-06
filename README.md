# LifeLine AI — Vercel-ready emergency experience

This project now runs as a fast, modern front end with serverless API routes that are ready to deploy on Vercel.

## What changed
- Rebuilt the experience around a polished, modern landing page with a dynamic 3D-inspired UI.
- Added Vercel-compatible API endpoints at `/api/health` and `/api/ambulance`.
- Kept the emergency-routing concept intact while making the app lightweight and deployment-friendly.

## Local checks
```bash
npm test
```

## Deploy to Vercel
1. Push this folder to GitHub.
2. Open Vercel and import the repository.
3. Vercel will detect the static app and serverless API automatically.
4. Deploy and visit the generated URL.

## Files
- `index.html` — the modern UI shell.
- `api/health.js` — health check endpoint.
- `api/ambulance.js` — nearest-hospital routing mock endpoint.
- `vercel.json` — Vercel routing configuration.
