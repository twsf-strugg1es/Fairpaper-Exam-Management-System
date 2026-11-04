"""Launch waitlist (PRD F27, AC22-AC23)."""
import csv
import re

import jwt

import manage_waitlist
from app import models, notify
from app.security import ALGORITHM, SECRET_KEY
from app.routers.waitlist import JOINED


def signups(db):
    return db.query(models.WaitlistSignup).all()


def test_ac22_join_once_with_the_same_answer_every_time(client, test_db):
    first = client.post("/waitlist", json={"email": "Rahim@School.edu ", "source": "landing-hero", "locale": "bn-BD"})
    again = client.post("/waitlist", json={"email": "rahim@school.edu"})

    assert first.status_code == again.status_code == 200
    assert first.json() == again.json() == {"message": JOINED}
    [row] = signups(test_db)
    assert row.email == "rahim@school.edu" and row.source == "landing-hero" and row.locale == "bn-BD"


def test_ac22_invalid_email_is_refused(client, test_db):
    res = client.post("/waitlist", json={"email": "not-an-email"})

    assert res.status_code == 422
    assert signups(test_db) == []


def test_the_api_never_returns_an_email(client, test_db):
    res = client.post("/waitlist", json={"email": "secret@school.edu"})

    assert "secret" not in res.text
    # No route lists the waitlist
    assert all(not (r.path.startswith("/waitlist") and "GET" in r.methods) for r in client.app.routes if hasattr(r, "methods"))


def test_honeypot_looks_the_same_but_stores_nothing(client, test_db):
    res = client.post("/waitlist", json={"email": "bot@spam.com", "website": "http://spam.example"})

    assert res.status_code == 200 and res.json() == {"message": JOINED}
    assert signups(test_db) == []


def test_odd_labels_are_dropped(client, test_db):
    client.post("/waitlist", json={"email": "a@b.com", "source": "<script>", "locale": "x" * 20})

    [row] = signups(test_db)
    assert row.source is None and row.locale == "x" * 20


def test_joining_is_rate_limited_per_ip(client, test_db):
    codes = [client.post("/waitlist", json={"email": f"p{i}@school.edu"}).status_code for i in range(21)]

    assert codes[:20] == [200] * 20 and codes[20] == 429


def test_ac23_launch_email_once_each_with_unsubscribe(client, test_db):
    notify.outbox.clear()
    for email in ("one@school.edu", "two@school.edu", "three@school.edu"):
        client.post("/waitlist", json={"email": email})

    # "three" unsubscribes before launch, from a link like the one in the email
    three = test_db.query(models.WaitlistSignup).filter_by(email="three@school.edu").one()
    token = manage_waitlist.unsubscribe_link(three).rsplit("/", 1)[1]
    assert client.post("/waitlist/unsubscribe", json={"token": token}).status_code == 200

    assert manage_waitlist.send_launch(test_db) == 2
    assert sorted(m.to for m in notify.outbox) == ["one@school.edu", "two@school.edu"]
    assert all(re.search(r"/waitlist/unsubscribe/\S+", m.text) for m in notify.outbox)

    # Running it again reaches nobody new
    assert manage_waitlist.send_launch(test_db) == 0
    assert len(notify.outbox) == 2


def test_unsubscribe_from_the_launch_email(client, test_db):
    notify.outbox.clear()
    client.post("/waitlist", json={"email": "later@school.edu"})
    manage_waitlist.send_launch(test_db)
    token = re.search(r"/waitlist/unsubscribe/(\S+)", notify.outbox[0].text).group(1)

    assert client.post("/waitlist/unsubscribe", json={"token": token}).status_code == 200
    assert client.post("/waitlist/unsubscribe", json={"token": token}).status_code == 200  # repeat clicks are fine
    assert signups(test_db)[0].unsubscribed_at is not None


def test_bad_unsubscribe_links(client, test_db):
    client.post("/waitlist", json={"email": "x@school.edu"})
    signup_id = str(signups(test_db)[0].id)
    tampered = manage_waitlist.unsubscribe_link(signups(test_db)[0]).rsplit("/", 1)[1][:-4] + "abcd"
    no_purpose = jwt.encode({"sub": signup_id}, SECRET_KEY, algorithm=ALGORITHM)  # shaped like a sign-in token

    assert client.post("/waitlist/unsubscribe", json={"token": "garbage"}).status_code == 400
    assert client.post("/waitlist/unsubscribe", json={"token": tampered}).status_code == 400
    assert client.post("/waitlist/unsubscribe", json={"token": no_purpose}).status_code == 400
    assert signups(test_db)[0].unsubscribed_at is None


def test_unsubscribe_token_is_not_a_sign_in_token(client, test_db):
    client.post("/waitlist", json={"email": "x@school.edu"})
    token = manage_waitlist.unsubscribe_link(signups(test_db)[0]).rsplit("/", 1)[1]

    assert client.get("/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_export_csv(client, test_db, tmp_path):
    client.post("/waitlist", json={"email": "csv@school.edu", "source": "landing-footer"})
    path = tmp_path / "waitlist.csv"

    assert manage_waitlist.export(test_db, str(path)) == 1
    with open(path, encoding="utf-8") as f:
        [row] = list(csv.DictReader(f))
    assert row["email"] == "csv@school.edu" and row["source"] == "landing-footer" and row["notified_at"] == ""


def test_send_launch_refuses_a_fake_sender(monkeypatch, capsys):
    monkeypatch.setenv("EMAIL_BACKEND", "console")

    assert manage_waitlist.main(["manage_waitlist.py", "send-launch"]) == 1
    assert "EMAIL_BACKEND=smtp" in capsys.readouterr().out


def test_joining_again_after_unsubscribing(client, test_db):
    client.post("/waitlist", json={"email": "back@school.edu"})
    token = manage_waitlist.unsubscribe_link(signups(test_db)[0]).rsplit("/", 1)[1]
    client.post("/waitlist/unsubscribe", json={"token": token})

    res = client.post("/waitlist", json={"email": "back@school.edu"})

    assert res.json() == {"message": JOINED}
    [row] = signups(test_db)
    test_db.refresh(row)
    assert row.unsubscribed_at is None
