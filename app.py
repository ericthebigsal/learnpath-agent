import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google import genai

import auth
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

SESSION_COOKIE_NAME = "session_token"


class NotAuthenticated(Exception):
    pass


@app.exception_handler(NotAuthenticated)
def handle_not_authenticated(request: Request, exc: NotAuthenticated):
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


def get_current_user(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token is None:
        raise NotAuthenticated()

    result = db.get_session_with_user(token, DB_PATH)
    if result is None:
        raise NotAuthenticated()

    expires_at = datetime.fromisoformat(result["session_expires_at"])
    if expires_at < datetime.now(timezone.utc):
        db.delete_session(token, DB_PATH)
        raise NotAuthenticated()

    return result


def get_owned_track(track_id: int, current_user: dict, db_path: str) -> dict:
    track = db.get_track(track_id, db_path)
    if track is None or track["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Track not found")
    return track


def compute_plan(learner: dict, progress: list[dict]) -> tuple[PlanResponse, bool, list[str]]:
    try:
        # google-genai's Client() only auto-detects GOOGLE_API_KEY, not
        # GEMINI_API_KEY (the name this project's README/plan document) —
        # pass it explicitly so the documented env var actually works.
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    except Exception:
        client = None
    return planner.plan_or_replan(client, CATALOG, learner, progress)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"request": request, "error": None})


@app.post("/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    if password != confirm_password:
        return templates.TemplateResponse(
            request, "register.html", {"request": request, "error": "Passwords don't match."}
        )

    if len(password) < 8:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"request": request, "error": "Password must be at least 8 characters."},
        )

    try:
        user = db.create_user(email, auth.hash_password(password), DB_PATH)
    except db.DuplicateEmailError:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"request": request, "error": "That email is already registered."},
        )

    token = auth.generate_session_token()
    expires_at = (datetime.now(timezone.utc) + auth.SESSION_DURATION).isoformat()
    db.create_session(token, user["id"], expires_at, DB_PATH)

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME, token, httponly=True, samesite="lax",
        max_age=int(auth.SESSION_DURATION.total_seconds()),
    )
    return response


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": None})


@app.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    user = db.get_user_by_email(email, DB_PATH)
    if user is None or not auth.verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"request": request, "error": "That email or password is incorrect."},
        )

    token = auth.generate_session_token()
    expires_at = (datetime.now(timezone.utc) + auth.SESSION_DURATION).isoformat()
    db.create_session(token, user["id"], expires_at, DB_PATH)

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME, token, httponly=True, samesite="lax",
        max_age=int(auth.SESSION_DURATION.total_seconds()),
    )
    return response


@app.post("/logout")
def logout_submit(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token is not None:
        db.delete_session(token, DB_PATH)

    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, current_user: dict = Depends(get_current_user)):
    tracks = db.get_tracks_for_user(current_user["id"], DB_PATH)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "tracks": tracks,
            "levels": [level.value for level in Level],
            "default_level": current_user["default_starting_level"],
        },
    )


@app.post("/tracks")
def create_track(
    goal_text: str = Form(...),
    starting_level: Level = Form(...),
    current_user: dict = Depends(get_current_user),
):
    name = auth.derive_track_name(goal_text)
    track = db.create_track(current_user["id"], name, goal_text, starting_level.value, DB_PATH)
    db.update_default_starting_level(current_user["id"], starting_level.value, DB_PATH)

    plan, _used_fallback, candidate_ids = compute_plan(track, [])
    plan_dict = plan.model_dump()
    plan_dict["candidate_ids"] = candidate_ids
    db.log_plan(track["id"], plan_dict, "initial", DB_PATH)
    return RedirectResponse(url=f"/path/{track['id']}", status_code=303)


@app.get("/path/{track_id}", response_class=HTMLResponse)
def current_path(
    request: Request, track_id: int, current_user: dict = Depends(get_current_user)
):
    track = get_owned_track(track_id, current_user, DB_PATH)
    progress = db.get_progress(track_id, DB_PATH)
    latest_plan = db.get_latest_plan(track_id, DB_PATH)
    if latest_plan is None:
        raise HTTPException(status_code=404, detail="Track not found")

    steps = [
        {"item": get_item(CATALOG, step["item_id"]), "rationale": step["rationale"]}
        for step in latest_plan["steps"]
    ]
    ready_tracks = planner.certification_ready_tracks(CATALOG, progress)
    candidates = [
        get_item(CATALOG, item_id) for item_id in latest_plan.get("candidate_ids", [])
    ]

    return templates.TemplateResponse(
        request,
        "path.html",
        {
            "request": request,
            "current_user": current_user,
            "track_id": track_id,
            "track": track,
            "steps": steps,
            "summary": latest_plan["summary"],
            "ready_tracks": ready_tracks,
            "candidates": candidates,
        },
    )


@app.get("/item/{track_id}/{item_id}", response_class=HTMLResponse)
def item_view(
    request: Request,
    track_id: int,
    item_id: str,
    current_user: dict = Depends(get_current_user),
):
    get_owned_track(track_id, current_user, DB_PATH)
    try:
        item = get_item(CATALOG, item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found")
    return templates.TemplateResponse(
        request,
        "item.html",
        {"request": request, "current_user": current_user, "track_id": track_id, "item": item},
    )


@app.get("/item/{track_id}/{item_id}/quiz", response_class=HTMLResponse)
def item_quiz_view(
    request: Request,
    track_id: int,
    item_id: str,
    current_user: dict = Depends(get_current_user),
):
    get_owned_track(track_id, current_user, DB_PATH)
    try:
        item = get_item(CATALOG, item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found")
    return templates.TemplateResponse(
        request,
        "item_quiz.html",
        {"request": request, "current_user": current_user, "track_id": track_id, "item": item},
    )


@app.post("/item/{track_id}/{item_id}/submit", response_class=HTMLResponse)
async def submit_quiz(
    request: Request,
    track_id: int,
    item_id: str,
    current_user: dict = Depends(get_current_user),
):
    track = get_owned_track(track_id, current_user, DB_PATH)
    form = await request.form()
    try:
        item = get_item(CATALOG, item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found")
    answers = [int(form.get(f"answer_{i}", -1)) for i in range(len(item.quiz))]
    score = quiz_module.grade_quiz(item.quiz, answers)

    db.record_progress(track_id, item_id, score, DB_PATH)

    previous_plan = db.get_latest_plan(track_id, DB_PATH)
    progress = db.get_progress(track_id, DB_PATH)
    new_plan, _used_fallback, candidate_ids = compute_plan(track, progress)
    new_plan_dict = new_plan.model_dump()
    new_plan_dict["candidate_ids"] = candidate_ids
    db.log_plan(track_id, new_plan_dict, "quiz_result", DB_PATH)

    old_item_ids = [step["item_id"] for step in previous_plan["steps"]] if previous_plan else []
    diff = planner.plan_diff(old_item_ids, [step.item_id for step in new_plan.steps])

    return templates.TemplateResponse(
        request,
        "path_updated.html",
        {
            "request": request,
            "current_user": current_user,
            "track_id": track_id,
            "score": score,
            "diff": diff,
            "summary": new_plan.summary,
        },
    )


@app.get("/history/{track_id}", response_class=HTMLResponse)
def history_page(
    request: Request, track_id: int, current_user: dict = Depends(get_current_user)
):
    get_owned_track(track_id, current_user, DB_PATH)
    progress = db.get_progress(track_id, DB_PATH)
    completed = [
        {
            "item": get_item(CATALOG, entry["item_id"]),
            "quiz_score": entry["quiz_score"],
            "completed_at": datetime.fromisoformat(entry["completed_at"]).strftime("%b %d, %Y"),
        }
        for entry in progress
    ]
    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "request": request,
            "current_user": current_user,
            "track_id": track_id,
            "completed": completed,
            "catalog": CATALOG.items,
        },
    )
