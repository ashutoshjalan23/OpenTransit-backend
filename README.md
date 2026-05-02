# OpenTransit Backend

This repository contains the Python backend for the COMP1110 Open Transit project.

## Endpoints

- `GET /`
- `GET /health`
- `GET /network`
- `GET /summary`
- `GET /eta?stopId=S01`
- `POST /plan`

`/network` includes stops, segments, and summary metrics. `/summary` returns only the summary metrics.

## Local Run

```bash
python -m pip install -r requirements.txt
python backend_api.py
```

Default local URL: `http://127.0.0.1:8000`

## Deployment

Production backend: [https://open-transit-backend.vercel.app](https://open-transit-backend.vercel.app)

Frontend Vercel environment variable:

```text
BACKEND_URL=https://open-transit-backend.vercel.app
```
