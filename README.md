# Queue Activity Report API

FastAPI service that builds **weekly** or **monthly** queue activity reports from MySQL operational tables (`PBX_QUEUEMON`, `PBX_AGENT`, optional `cdr`). All aggregation is done in SQL and/or Python — there is no summary table.

## Features

- `POST /reports/queue-activity` — JSON body (Pydantic), JSON response
- Header **`X-API-Key`** required (set `API_KEY` in `.env`)
- **Async MySQL** via `aiomysql`; independent queries run with `asyncio.gather`
- **In-memory cache** — 10 second TTL per report request key (`cachetools.TTLCache`)
  - **Limitation:** cache is **per process**. Multiple Uvicorn/Gunicorn workers each hold separate caches.
- Optional **`httpx`** async client pattern for future external HTTP calls (see `app/http_client.py`)

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# edit .env with real DB credentials and API_KEY
```

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open docs: `http://localhost:8000/docs`

## Example request

```bash
curl -X POST "http://localhost:8000/reports/queue-activity" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: YOUR_API_KEY" ^
  -d "{\"period_type\":\"weekly\",\"year\":2026,\"week\":20,\"queues\":[\"sales\"]}"
```

## Tests

```bash
pytest -q
```

## Project layout

```
app/
  main.py           # FastAPI app, lifespan, routers
  config.py         # Settings
  database.py       # aiomysql pool
  cache.py          # TTL 10s report cache
  dependencies.py # API key
  http_client.py    # shared AsyncClient (optional external calls)
  routers/reports.py
  schemas/request.py, response.py
  services/queue_report.py
tests/
```
