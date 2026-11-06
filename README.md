# RouteWise

RouteWise is an LLM routing gateway. It analyzes each prompt, selects a
lower-cost or stronger model, calls the provider, and returns the answer
through a web playground or an OpenAI-compatible API.

## Live application

- [Playground](https://switchyard-3l2r.onrender.com/)
- [Dashboard](https://switchyard-3l2r.onrender.com/dashboard)
- [Health check](https://switchyard-3l2r.onrender.com/healthz)
- [Readiness check](https://switchyard-3l2r.onrender.com/readyz)
- [Model discovery](https://switchyard-3l2r.onrender.com/v1/models)
- [GitHub repository](https://github.com/Asmitcod/switchyard)

The playground shows the answer, selected tier, exact provider model, estimated
cost, and routing latency. Use the dashboard after submitting prompts to view
request counts, cheap-model share, estimated savings, and recent routing data.

## How a user uses it

1. Open the [playground](https://switchyard-3l2r.onrender.com/).
2. Enter a prompt or choose an example.
3. Submit the prompt.
4. Read the answer and see which model generated it.
5. Open the [dashboard](https://switchyard-3l2r.onrender.com/dashboard) to
   inspect routing activity.

If API protection is enabled, the browser asks for the value configured as
`ROUTEWISE_API_KEYS`. Never use or share the Groq provider key with end users.
The browser keeps the RouteWise key only in the current session.

## Models and routing

The current deployment uses Groq's OpenAI-compatible API:

- Cheap tier: `openai/gpt-oss-20b`
- Strong tier: `openai/gpt-oss-120b`

The default routing threshold is `0.60`. Prompts scoring at least the threshold
use the cheap tier; lower-scoring prompts use the strong tier. The deterministic
router considers prompt length, easy terms, difficult terms, math patterns, and
code patterns. If a provider fails, RouteWise tries the other configured tier.

The trained router is opt-in and remains disabled by default until evaluation
shows reliable generalization on unseen categories. Enable it only after
reviewing the evaluation output:

```text
ROUTEWISE_USE_TRAINED_MODEL=true
```

## OpenAI-compatible API

Use the RouteWise API key, not the Groq key:

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_ROUTEWISE_API_KEY",
    base_url="https://switchyard-3l2r.onrender.com/v1",
)

response = client.chat.completions.create(
    model="routewise",
    messages=[{"role": "user", "content": "Explain recursion simply."}],
)

print(response.choices[0].message.content)
```

Streaming is supported:

```python
response = client.chat.completions.create(
    model="routewise",
    messages=[{"role": "user", "content": "Write a Python function."}],
    stream=True,
)

for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

Direct HTTP example:

```powershell
curl.exe https://switchyard-3l2r.onrender.com/v1/chat/completions `
  -H "Authorization: Bearer YOUR_ROUTEWISE_API_KEY" `
  -H "Content-Type: application/json" `
  -d '{\"model\":\"routewise\",\"messages\":[{\"role\":\"user\",\"content\":\"What is photosynthesis?\"}]}'
```

## Configuration

Copy the safe template:

```powershell
Copy-Item .env.example .env
```

Set these values locally or in Render:

```text
GROQ_API_KEY=your-provider-key
CHEAP_MODEL=openai/gpt-oss-20b
STRONG_MODEL=openai/gpt-oss-120b
GROQ_BASE_URL=https://api.groq.com/openai/v1
DATABASE_URL=your-neon-connection-string
ROUTEWISE_API_KEYS=your-client-key
ROUTEWISE_RATE_LIMIT=60
ROUTEWISE_USE_TRAINED_MODEL=false
```

`GROQ_API_KEY` is used only by the server to call Groq. `ROUTEWISE_API_KEYS`
protects your application from unauthorized users and is the key clients use.
Keep both private. `.env` and generated datasets/models are ignored by Git.

## Local development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/` for the playground and
`http://127.0.0.1:8000/dashboard` for the dashboard.

## Operations

- `/healthz` confirms that the process is alive.
- `/readyz` reports whether both model tiers are configured.
- `/api/status` reports provider, storage, and trained-router state without
  exposing credentials. It is protected when API keys are configured.
- `/v1/models` lists the RouteWise model and configured provider tiers.

Request logs contain metadata and SHA-256 prompt hashes, not raw prompts.
Neon/Postgres is used when `DATABASE_URL` is configured; temporary database
connectivity failures fall back to SQLite.

## Tests and deployment

Run checks:

```powershell
python -m pytest -q
python -m compileall -q app scripts
```

Build and run Docker:

```powershell
docker build -t switchyard .
docker run --env-file .env -p 8000:8000 switchyard
```

Render uses [`render.yaml`](./render.yaml) and [`start.sh`](./start.sh).
GitHub Actions runs tests, compilation, and the Docker build on pushes and
pull requests.

## Dataset collection and training

With both provider models configured:

```powershell
python scripts/collect_dataset.py --limit 16
python scripts/train_router.py
python scripts/evaluate_router.py
```

The collector is resumable. Generated datasets, evaluation output, SQLite
logs, and trained model files are intentionally ignored by Git. Do not enable
the trained router solely from a small smoke dataset.

## Security

The API key previously pasted into chat must be treated as compromised. Rotate
it in Render immediately and use a newly generated value for
`ROUTEWISE_API_KEYS`. Never put live keys in README files, source code, issues,
screenshots, or Git history.
