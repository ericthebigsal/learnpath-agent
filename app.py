from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google import genai

import db
import planner
import quiz as quiz_module
from catalog import get_item, load_catalog
from models import Level, PlanResponse

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "learnpath.db")
CATALOG = load_catalog()

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

db.init_db(DB_PATH)


def compute_plan(learner: dict, progress: list[dict]) -> tuple[PlanResponse, bool]:
    try:
        client = genai.Client()
    except Exception:
        client = None
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


@app.get("/path/{learner_id}", response_class=HTMLResponse)
def current_path(request: Request, learner_id: int):
    learner = db.get_learner(learner_id, DB_PATH)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    progress = db.get_progress(learner_id, DB_PATH)
    latest_plan = db.get_latest_plan(learner_id, DB_PATH)

    steps = [
        {"item": get_item(CATALOG, step["item_id"]), "rationale": step["rationale"]}
        for step in latest_plan["steps"]
    ]
    ready_tracks = planner.certification_ready_tracks(CATALOG, progress)

    return templates.TemplateResponse(
        request,
        "path.html",
        {
            "request": request,
            "learner_id": learner_id,
            "learner": learner,
            "steps": steps,
            "summary": latest_plan["summary"],
            "ready_tracks": ready_tracks,
        },
    )


@app.get("/item/{learner_id}/{item_id}", response_class=HTMLResponse)
def item_view(request: Request, learner_id: int, item_id: str):
    try:
        item = get_item(CATALOG, item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found")
    return templates.TemplateResponse(
        request,
        "item.html",
        {"request": request, "learner_id": learner_id, "item": item},
    )


@app.post("/item/{learner_id}/{item_id}/submit", response_class=HTMLResponse)
async def submit_quiz(request: Request, learner_id: int, item_id: str):
    form = await request.form()
    try:
        item = get_item(CATALOG, item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found")
    answers = [int(form.get(f"answer_{i}", -1)) for i in range(len(item.quiz))]
    score = quiz_module.grade_quiz(item.quiz, answers)

    learner = db.get_learner(learner_id, DB_PATH)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    db.record_progress(learner_id, item_id, score, DB_PATH)

    previous_plan = db.get_latest_plan(learner_id, DB_PATH)
    progress = db.get_progress(learner_id, DB_PATH)
    new_plan, _used_fallback = compute_plan(learner, progress)
    db.log_plan(learner_id, new_plan.model_dump(), "quiz_result", DB_PATH)

    old_item_ids = [step["item_id"] for step in previous_plan["steps"]] if previous_plan else []
    diff = planner.plan_diff(old_item_ids, [step.item_id for step in new_plan.steps])

    return templates.TemplateResponse(
        request,
        "path_updated.html",
        {
            "request": request,
            "learner_id": learner_id,
            "score": score,
            "diff": diff,
            "summary": new_plan.summary,
        },
    )


@app.get("/history/{learner_id}", response_class=HTMLResponse)
def history_page(request: Request, learner_id: int):
    learner = db.get_learner(learner_id, DB_PATH)
    if learner is None:
        raise HTTPException(status_code=404, detail="Learner not found")
    plan_log = db.get_plan_log(learner_id, DB_PATH)
    return templates.TemplateResponse(
        request,
        "history.html",
        {"request": request, "learner_id": learner_id, "plan_log": plan_log, "catalog": CATALOG.items},
    )
