# OpenTransit Backend

This repository contains the Python backend for the COMP1110 Open Transit project.

## Endpoints

- `GET /`
- `GET /health`
- `GET /network`
- `GET /eta?stopId=S01`
- `POST /plan`

## Local Run

```bash
python -m pip install -r requirements.txt
python backend_api.py
```

Default local URL: `http://127.0.0.1:8000`

## Deployment

Production backend: [https://open-transit-backend.vercel.app](https://open-transit-backend.vercel.app)

The server supports Vercel serverless deployment through `api/index.py`, and Railway/Heroku-style deployment through `backend_api.py`:

- `PORT` is used automatically when provided by the hosting platform.
- `HOST` is used automatically when provided, otherwise the server binds to `0.0.0.0`.
- The older `HK_TRANSIT_BACKEND_PORT` and `HK_TRANSIT_BACKEND_HOST` variables still work for local overrides.

After deploying this backend, set the frontend repo's Vercel environment variable:

```text
BACKEND_URL=https://open-transit-backend.vercel.app
```

The frontend will call the backend through its same-origin `/api/backend/...` proxy.
