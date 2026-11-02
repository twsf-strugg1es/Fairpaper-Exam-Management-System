"""Seed one exam day for the load test (task 5.2), through the API, so it works against any environment.

Creates an organization with its owner, a mixed 30-question exam that is open now, and the candidates (they sign
up with the organization's join code). Writes everything locustfile.py needs to candidates.json.

    python loadtest/seed.py --api https://staging-api.example.com --candidates 500

Run it once per load test: every candidate can start the exam only once, and the test submits at the end.
"""
import argparse
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

QUESTIONS = [
    {"type": "single_choice", "options": ["Dhaka", "Chattogram", "Khulna", "Sylhet"], "correct_answers": "Dhaka"},
    {"type": "multi_choice", "options": ["Iron", "Wood", "Copper", "Glass"], "correct_answers": ["Iron", "Copper"]},
    {"type": "true_false", "correct_answers": "true"},
    {"type": "numeric", "correct_answers": {"value": 9.8, "tolerance": 0.1}},
    {"type": "text"},
]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", required=True, help="the API's base URL")
    parser.add_argument("--candidates", type=int, default=500)
    parser.add_argument("--questions", type=int, default=30)
    parser.add_argument("--password", default="load-test-password-1", help="every account's password")
    parser.add_argument("--out", default="candidates.json")
    args = parser.parse_args()
    api, run = args.api.rstrip("/"), uuid.uuid4().hex[:8]
    http = requests.Session()

    def ok(res):
        if res.status_code >= 300:
            raise SystemExit(f"{res.request.method} {res.url} -> {res.status_code}: {res.text[:300]}")
        return res.json()

    owner = f"loadtest-{run}-owner@example.com"
    ok(http.post(f"{api}/signup/organization", json={
        "email": owner, "password": args.password, "full_name": "Load test owner",
        "organization_name": f"Load test {run}", "timezone": "Asia/Dhaka"}))
    token = ok(http.post(f"{api}/token", data={"username": owner, "password": args.password}))["access_token"]
    me = ok(http.get(f"{api}/me", headers={"Authorization": f"Bearer {token}"}))
    org_id = me["memberships"][0]["organization_id"]
    staff = {"Authorization": f"Bearer {token}", "X-Organization-Id": org_id}
    join_code = ok(http.get(f"{api}/org", headers=staff))["join_code"]

    ids = []
    for i in range(args.questions):
        body = QUESTIONS[i % len(QUESTIONS)]
        ids.append(ok(http.post(f"{api}/admin/questions/", headers=staff, json={
            "title": f"Question {i + 1} ({body['type']})", "complexity": "medium", "max_score": 1, **body}))["id"])
    now = datetime.now(timezone.utc)
    exam = ok(http.post(f"{api}/admin/exams/", headers=staff, json={
        "title": f"Load test {run}", "start_time": (now - timedelta(minutes=1)).isoformat(),
        "end_time": (now + timedelta(hours=3)).isoformat(), "duration_minutes": 120, "question_ids": ids,
        "require_fullscreen": False, "results_release": "on_close"}))
    ok(http.post(f"{api}/admin/exams/{exam['id']}/publish", headers=staff))

    def sign_up(i):
        email = f"loadtest-{run}-{i:04d}@example.com"
        ok(requests.post(f"{api}/signup", json={"email": email, "password": args.password,
                                                "full_name": f"Candidate {i + 1}", "join_code": join_code}))
        return {"email": email, "password": args.password}

    with ThreadPoolExecutor(max_workers=8) as pool:
        candidates = list(pool.map(sign_up, range(args.candidates)))
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"api": api, "organization_id": org_id, "exam_id": exam["id"], "candidates": candidates}, f, indent=1)
    print(f"Exam {exam['id']} with {len(ids)} questions, {len(candidates)} candidates -> {args.out}")


if __name__ == "__main__":
    main()
