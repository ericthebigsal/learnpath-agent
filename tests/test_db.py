import db


def test_init_db_is_idempotent(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.init_db(db_path)  # must not raise on a second call


def test_create_and_get_learner(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)

    learner = db.create_learner("Learn RAG basics", "beginner", db_path)

    assert learner["goal_text"] == "Learn RAG basics"
    assert learner["starting_level"] == "beginner"
    assert isinstance(learner["id"], int)

    fetched = db.get_learner(learner["id"], db_path)
    assert fetched == learner

    assert db.get_learner(9999, db_path) is None


def test_record_and_get_progress(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    learner = db.create_learner("Learn RAG basics", "beginner", db_path)

    db.record_progress(learner["id"], "rag-fundamentals", 85.0, db_path)
    db.record_progress(learner["id"], "rag-chunking-strategies", 60.0, db_path)

    progress = db.get_progress(learner["id"], db_path)

    assert len(progress) == 2
    assert progress[0]["item_id"] == "rag-fundamentals"
    assert progress[0]["quiz_score"] == 85.0
    assert progress[1]["item_id"] == "rag-chunking-strategies"


def test_log_plan_and_get_latest_plan(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    learner = db.create_learner("Learn RAG basics", "beginner", db_path)

    plan = {
        "steps": [{"item_id": "rag-fundamentals", "rationale": "Matches your goal."}],
        "summary": "Start with RAG fundamentals.",
    }
    logged = db.log_plan(learner["id"], plan, "initial", db_path)

    assert logged["trigger"] == "initial"
    assert logged["steps"] == plan["steps"]
    assert logged["summary"] == plan["summary"]

    latest = db.get_latest_plan(learner["id"], db_path)
    assert latest["steps"] == plan["steps"]
    assert latest["summary"] == plan["summary"]


def test_get_latest_plan_returns_none_when_no_plans_logged(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    learner = db.create_learner("Learn RAG basics", "beginner", db_path)

    assert db.get_latest_plan(learner["id"], db_path) is None


def test_get_plan_log_returns_all_plans_in_order(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    learner = db.create_learner("Learn RAG basics", "beginner", db_path)

    db.log_plan(learner["id"], {"steps": [], "summary": "first"}, "initial", db_path)
    db.log_plan(learner["id"], {"steps": [], "summary": "second"}, "quiz_result", db_path)

    log = db.get_plan_log(learner["id"], db_path)

    assert [entry["summary"] for entry in log] == ["first", "second"]
    assert [entry["trigger"] for entry in log] == ["initial", "quiz_result"]
