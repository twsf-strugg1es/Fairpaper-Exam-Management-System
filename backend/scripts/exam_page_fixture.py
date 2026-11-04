"""Writes frontend/src/pages/__fixtures__/examPage.json: real API responses for one exam, for the exam page's tests.

    cd backend && DATABASE_URL=sqlite:///:memory: SECRET_KEY=<32+ characters> python scripts/exam_page_fixture.py

Re-run it when the candidate payloads change, so the frontend tests keep matching the API.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tests.conftest  # noqa: E402,F401  (SQLite UUID columns as text, test email backend)
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from tests.test_organizations import headers_for, make_org, make_user  # noqa: E402

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(bind=engine)
db = sessionmaker(bind=engine, autoflush=False)()
app.dependency_overrides[get_db] = lambda: (yield db)
client = TestClient(app)

org = make_org(db, "Fixture School")
staff = headers_for(make_user(db, "owner@fixture.com", org, models.ROLE_OWNER), org)
kid = headers_for(make_user(db, "kid@fixture.com", org, models.ROLE_CANDIDATE), org)
ids = [client.post("/admin/questions/", headers=staff, json=q).json()["id"] for q in (
    {"title": "What is 2 + 2?", "complexity": "easy", "type": "single_choice", "options": ["3", "4", "5"], "correct_answers": "4", "max_score": 1},
    {"title": "Water boils at 100 °C at sea level.", "complexity": "easy", "type": "true_false", "correct_answers": "true", "max_score": 1},
)]
now = datetime.now(timezone.utc)
exam = client.post("/admin/exams/", headers=staff, json={
    "title": "Fixture quiz", "start_time": (now - timedelta(minutes=5)).isoformat(), "end_time": (now + timedelta(days=3650)).isoformat(),
    "duration_minutes": 30, "question_ids": ids, "require_fullscreen": False, "shuffle_questions": False, "shuffle_options": False}).json()
client.post(f"/admin/exams/{exam['id']}/publish", headers=staff)

out = {"exams": client.get("/student/exams/", headers=kid).json(), "unfinished": []}
session = client.post(f"/student/exams/{exam['id']}/start", headers=kid).json()
attempt = session["attempt"]["id"]
out["session"] = session
out["answers"] = client.get(f"/student/attempts/{attempt}/answers", headers=kid).json()
out["save"] = client.post(f"/student/attempts/{attempt}/save-answer", headers=kid, json={"question_id": ids[0], "answer_data": "4", "client_seq": 1}).json()
out["clock"] = client.get(f"/student/attempts/{attempt}/clock", headers=kid).json()
out["submit"] = client.post(f"/student/attempts/{attempt}/submit", headers=kid).json()
out["results"] = client.get(f"/student/attempts/{attempt}/results", headers=kid).json()
target = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "__fixtures__" / "examPage.json"
target.parent.mkdir(exist_ok=True)
target.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print("wrote", target)
