# learnpath-agent

A small FastAPI app that simulates an Amazon-Ads-Academy-shaped course catalog — course/learning-path/video content types, three levels, tagged tracks, a dual certification model — except the content teaches modern AI/agentic concepts (RAG, multi-agent systems, LLM evaluation, agent tooling, context engineering, LLM billing). The centerpiece is an **adaptive learning-path agent**: instead of routing a learner through one of the catalog's fixed "Learning Path" bundles, an LLM plans a personalized sequence from a learner's stated goal and level, and re-plans it after every quiz result.

## Why this exists

Static "personalized learning paths" in most real LMS products are personalized once, at signup, and then static. This project builds the more interesting version: a planner that re-plans after every quiz result — inserting a remedial item on a weak score, skipping ahead on a strong one, and always showing its work (candidates it could have picked, and why it picked what it did).

## How it works

- `catalog.py` / `data/catalog.json` — ~54 seed items across 7 AI-concept tracks and 3 levels.
- `planner.py` — filters the catalog down to a relevant candidate set, then either asks Gemini (structured JSON output validated against a Pydantic schema) to rank/sequence them with rationale, or falls back to a deterministic rule-based planner if the API call fails or rate-limits.
- `db.py` — SQLite-backed learner state: goal, progress, and every past plan with its rationale.
- `app.py` — five FastAPI screens: start → current path → item + quiz → path-updated diff → plan history / catalog browse.

Every function that calls the Gemini API takes the client as an explicit parameter, and `genai.Client()` is constructed in exactly one place (`app.compute_plan`). That's what makes the entire automated test suite run offline, with a mocked client and no API key required.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the test suite (no API key needed — everything's mocked)
pytest -v

# Run the real app (requires a real Gemini key for the planner to actually call the LLM;
# falls back to the rule-based planner automatically if GEMINI_API_KEY is unset or the call fails)
export GEMINI_API_KEY="AIza..."
uvicorn app:app --reload
```

Then open http://127.0.0.1:8000/, describe a learning goal (e.g. "I want to understand how RAG differs from just stuffing context into a prompt"), and follow the generated path — completing items and taking their quizzes to watch the plan adapt.

## Tech stack

Python, FastAPI, Jinja2, Pydantic v2, `google-genai` (Gemini free tier, `gemini-2.5-flash`), SQLite, pytest.
