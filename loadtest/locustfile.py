"""Exam day under load (task 5.2).

Every simulated candidate signs in, opens their exam list and starts the exam. Then they write for as long as
the test runs, the way the exam page does: an answer saved every 10 to 30 seconds, the clock checked once a minute,
and now and then a focus change reported. When the test stops, every candidate submits.

Targets (02-TRD "Performance and reliability targets"): starting the exam p95 < 1.5 s with 500 candidates
starting within a minute, and saving an answer p95 < 500 ms at 500 concurrent candidates. The run exits with
code 1 when either is missed or any request fails.

    locust -f loadtest/locustfile.py --host https://staging-api.example.com --headless -u 500 -r 9 -t 10m --csv loadtest/results
"""
import itertools
import json
import os
import random
import time

from locust import HttpUser, between, events, task

with open(os.getenv("LOADTEST_SEED", "candidates.json"), encoding="utf-8") as f:
    SEED = json.load(f)
ACCOUNTS = itertools.cycle(SEED["candidates"])
TARGETS = {("POST", "start exam"): 1500, ("POST", "save answer"): 500}  # p95, milliseconds


def answer_for(question):
    options = question.get("options")
    return {
        "single_choice": lambda: random.choice(options),
        "multi_choice": lambda: random.sample(options, 2),
        "true_false": lambda: random.choice(["true", "false"]),
        "numeric": lambda: str(round(random.uniform(9, 11), 1)),
    }.get(question["type"], lambda: "Light bends because it changes speed between materials. " * 3)()


class Candidate(HttpUser):
    wait_time = between(10, 30)

    def on_start(self):
        account = next(ACCOUNTS)
        res = self.client.post("/token", data={"username": account["email"], "password": account["password"]}, name="sign in")
        self.headers = {"Authorization": f"Bearer {res.json()['access_token']}", "X-Organization-Id": SEED["organization_id"]}
        self.client.get("/student/exams/", headers=self.headers, name="exam list")
        session = self.client.post(f"/student/exams/{SEED['exam_id']}/start", headers=self.headers, name="start exam").json()
        self.attempt = session["attempt"]["id"]
        self.questions = session["exam"]["questions"]
        self.saves = 0
        self.clock_checked = time.monotonic()

    @task
    def write(self):
        if time.monotonic() - self.clock_checked >= 60:
            self.client.get(f"/student/attempts/{self.attempt}/clock", headers=self.headers, name="clock")
            self.clock_checked = time.monotonic()
        question = random.choice(self.questions)
        self.saves += 1
        self.client.post(f"/student/attempts/{self.attempt}/save-answer", headers=self.headers, name="save answer",
                         json={"question_id": question["id"], "answer_data": answer_for(question), "client_seq": self.saves})
        if random.random() < 0.05:
            self.client.post(f"/student/attempts/{self.attempt}/events", headers=self.headers, name="focus change",
                             json={"events": [{"type": "focus_lost"}, {"type": "focus_returned"}]})

    def on_stop(self):
        if getattr(self, "attempt", None):
            self.client.post(f"/student/attempts/{self.attempt}/submit", headers=self.headers, name="submit")


@events.quitting.add_listener
def check_targets(environment, **_):
    failed = environment.stats.total.num_failures
    for (method, name), limit in TARGETS.items():
        entry = environment.stats.get(name, method)
        p95 = entry.get_response_time_percentile(0.95) if entry.num_requests else None
        passed = p95 is not None and p95 <= limit
        print(f"{name}: p95 {p95 or 0:.0f} ms (target < {limit} ms) over {entry.num_requests} requests: {'pass' if passed else 'FAIL'}")
        if not passed:
            environment.process_exit_code = 1
    print(f"failed requests: {failed}")
    if failed:
        environment.process_exit_code = 1
