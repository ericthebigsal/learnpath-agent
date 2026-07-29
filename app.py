from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google import genai

import db
import planner
from catalog import load_catalog
from models import Level, PlanResponse

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "learnpath.db")
CATALOG = load_catalog()

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

db.init_db(DB_PATH)


def compute_plan(learner: dict, progress: list[dict]) -> tuple[PlanResponse, bool]:
    client = genai.Client()
    return planner.plan_or_replan(client, CATALOG, learner, progress)


@app.get("/", response_class=HTMLResponse)
def start_page(request: Request):
    return templates.TemplateResponse(
        request,
        "start.html",
        {"request": request, "levels": [level.value for level in Level]},
    )


@app.post("/start")
def start_learner(goal_text: str = Form(...), starting_level: str = Form(...)):
    learner = db.create_learner(goal_text, starting_level, DB_PATH)
    plan, _used_fallback = compute_plan(learner, [])
    db.log_plan(learner["id"], plan.model_dump(), "initial", DB_PATH)
    return RedirectResponse(url=f"/path/{learner['id']}", status_code=303)
