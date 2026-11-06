# RouteWise

RouteWise is a learned LLM router that keeps the supplied playground and dashboard UI while exposing a backend API for routing decisions.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/` for the playground and `http://127.0.0.1:8000/dashboard` for the dashboard.

Health endpoints:

- `/healthz` confirms the process is running.
- `/readyz` reports whether both model tiers are configured without revealing credentials.
- `/api/status` reports configured provider and storage state without returning secrets. It uses the configured API key protection.

Run the automated checks with:

```powershell
pytest
```

Build the deployment image with:

```powershell
docker build -t switchyard .
docker run --env-file .env -p 8000:8000 switchyard
```

GitHub Actions runs compilation and the automated test suite on pushes and pull requests.
CI also builds the Docker image to catch deployment packaging errors before release.

`render.yaml` and `start.sh` provide a deployment starting point for a Docker-based free web service. Add the secrets in the hosting provider dashboard; never commit them.

The easiest setup is:

```powershell
Copy-Item .env.example .env
```

Then open `.env` and paste your Groq key here:

```text
GROQ_API_KEY=paste-your-key-here
```

Do not add quotes or share the file contents. `.env` is ignored by Git.

The backend currently uses a deterministic heuristic router so the UI and API can be tested without provider credentials. The copied template already configures the selected Groq models:

```powershell
$env:GROQ_API_KEY="your-key"
```

The proxy is available at `POST /v1/chat/completions`. It routes to the selected tier and retries the other configured tier when the first provider fails. Request metadata is persisted locally in `data/routewise.sqlite3`; raw prompts are never stored, only SHA-256 hashes. Set `ROUTEWISE_SQLITE_PATH` to use another local database path. When `DATABASE_URL` is configured, the same schema is stored in Neon/Postgres; temporary database connectivity failures fall back to SQLite.

The Groq connection has been tested locally with the configured GPT OSS models. Empty upstream assistant responses are treated as provider failures so the configured fallback can be attempted.

For deployment, set `ROUTEWISE_API_KEYS` to one or more comma-separated client keys. Clients send `Authorization: Bearer <key>`. Requests are limited to 60 per minute per configured key by default; change `ROUTEWISE_RATE_LIMIT` to adjust the limit. Authentication is disabled only when `ROUTEWISE_API_KEYS` is empty, which is convenient for local development.

`POST /v1/chat/completions` also supports `stream: true` and returns OpenAI-compatible server-sent events.

`GET /v1/models` exposes the configured RouteWise model and provider tiers for OpenAI-compatible client discovery.

## Collect and train a first router

With both Groq models configured, run the resumable collection job:

```powershell
python scripts/collect_dataset.py --limit 16
python scripts/train_router.py
python scripts/evaluate_router.py
```

The collector stores model responses and verifiable labels in `data/router_dataset.jsonl`. It can be interrupted and rerun; completed prompts are skipped. The first model is intentionally a small baseline dataset, not the final 4,000–6,000 prompt benchmark described in the requirements.

Set `ROUTEWISE_USE_TRAINED_MODEL=true` after collecting a sufficiently large, representative dataset. When enabled and `data/router_model.pkl` exists, the API loads it for routing scores. If it is absent or invalid, the deterministic heuristic remains active so a fresh clone still runs.

The evaluator uses a deterministic held-out split, category-held-out tests, bootstrap 95% confidence intervals, and score-bin calibration. Do not enable the trained router based on the current smoke benchmark: it has only 19 held-out examples and the calibration is not yet reliable.
