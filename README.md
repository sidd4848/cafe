# Cafe Companion

An AI layer over a café visit: conversational ordering, live and predicted waits, pre-ordering,
personalised discovery, dine-in floor management with QR table checkout, and "Connect" for
meeting people at the café within a 24-hour window.

- **Design:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **GCP project:** `stockscreenerai-6f441` · region `asia-south1` · Firestore DB `cafedata`
- **Services:** `cafe-api` (FastAPI) and `cafe-web` (nginx + React), both on Cloud Run with no load balancer

```
backend/     FastAPI app (app/), seed script, unit tests      -> Cloud Run: cafe-api
frontend/    React + Vite + Tailwind SPA, nginx image          -> Cloud Run: cafe-web
firestore/   security rules + indexes for cafedata
deploy/      deploy.sh (build, deploy, CORS, auth domain, scheduler)
```

## Roles and sign-in

| Who | Where | How they get the role |
|---|---|---|
| Customer | `/login` | Google or email/password; anyone can register |
| Employee (staff) | `/staff/login` | A manager invites their email under **Staff → Team** |
| Manager | `/staff/login` | Emails in `BOOTSTRAP_MANAGERS` (set in `deploy.sh`) become managers on first sign-in |

Roles are a Firebase custom claim (`role`). The API enforces them on every route, and the
Firestore rules use the same claim for the realtime listeners.

## Local development

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
```

```bash
cd backend && PYTHONPATH=. .venv/Scripts/uvicorn app.main:app --port 8080 --reload
```

```bash
cd frontend && npm install && npm run dev
```

The backend uses your gcloud Application Default Credentials. `frontend/.env` holds the Firebase web
config (see `.env.example`).

## One-time setup (already done for this project)

```bash
firebase deploy --only firestore --project stockscreenerai-6f441
```

```bash
cd backend && PYTHONPATH=. .venv/Scripts/python -m scripts.seed
```

TTL policies on `expiresAt` are enabled for: `orderSessions`, `presence`, `sparks`, `connections`,
`messages` and `waitlist`.

## Deploy

```bash
bash deploy/deploy.sh
```

## Tests

```bash
cd backend && PYTHONPATH=. .venv/Scripts/python -m pytest -q tests
```

## Notes

- Payments are **simulated**: no card or UPI details are collected, and transaction IDs start with `DEMO-`.
- The menu is modelled on a third-wave specialty-coffee lineup (in the style of Third Wave Coffee, India),
  with approximate prices and nutrition.
- Weather comes from Open-Meteo using only the café's coordinates.
