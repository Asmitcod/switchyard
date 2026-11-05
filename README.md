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

The proxy is available at `POST /v1/chat/completions`. It routes to the selected tier and retries the other configured tier when the first provider fails. Raw prompts are not persisted by the current in-memory request log; persistent database logging will be added next.
