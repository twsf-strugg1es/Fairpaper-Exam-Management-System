"""Signing in and staying signed in (task 5.1). Passwords follow one rule on the server, Account settings take only
well-formed values, wrong current passwords are limited, and changing or resetting a password signs out every other
session, a stolen token and its refreshes included."""
import re
from datetime import datetime, timedelta, timezone

import jwt

from app import notify
from app.security import ALGORITHM, SECRET_KEY
from tests.test_organizations import make_user

PASSWORD = "Password123!"  # make_user's


def _sign_in(client, email, password=PASSWORD):
    res = client.post("/token", data={"username": email, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _change(client, headers, old=PASSWORD, new="a-new-password-1"):
    return client.post("/profile/change-password", headers=headers, json={"old_password": old, "new_password": new})


def test_changing_the_password_signs_out_every_other_session(client, test_db):
    user = make_user(test_db, "kid@sessions.com")
    laptop, phone = _sign_in(client, user.email), _sign_in(client, user.email)
    res = _change(client, laptop)
    assert res.status_code == 200, res.text
    fresh = {"Authorization": f"Bearer {res.json()['access_token']}"}

    assert client.get("/me", headers=fresh).status_code == 200  # the page that changed it carries on
    assert client.get("/me", headers=phone).status_code == 401
    assert client.get("/me", headers=laptop).status_code == 401
    assert client.post("/token/refresh", headers=phone).status_code == 401  # a stolen token can't renew itself
    assert client.post("/token", data={"username": user.email, "password": PASSWORD}).status_code == 400
    assert client.get("/me", headers=_sign_in(client, user.email, "a-new-password-1")).status_code == 200


def test_a_reset_link_signs_out_every_session(client, test_db):
    user = make_user(test_db, "reset@sessions.com")
    before = _sign_in(client, user.email)
    notify.outbox.clear()
    assert client.post("/password-reset/request", json={"email": user.email}).status_code == 200
    token = re.search(r"/reset-password/([\w-]+)", notify.outbox[-1].text).group(1)
    assert client.post("/password-reset/confirm", json={"token": token, "new_password": "brand-new-1"}).status_code == 200

    assert client.get("/me", headers=before).status_code == 401
    assert client.get("/me", headers=_sign_in(client, user.email, "brand-new-1")).status_code == 200


def test_tokens_from_before_this_release_work_until_the_password_changes(client, test_db):
    user = make_user(test_db, "old@sessions.com")
    claims = {"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(minutes=30)}  # no `iat` back then
    old = {"Authorization": f"Bearer {jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)}"}
    assert client.get("/me", headers=old).status_code == 200

    assert _change(client, _sign_in(client, user.email)).status_code == 200
    assert client.get("/me", headers=old).status_code == 401


def test_the_server_holds_every_password_to_the_same_rule(client, test_db):
    assert client.post("/signup", json={"email": "short@sessions.com", "password": "1234567"}).status_code == 422
    assert client.post("/signup/organization", json={
        "email": "owner@sessions.com", "password": "1234567", "organization_name": "Short Coaching"}).status_code == 422
    user = make_user(test_db, "change@sessions.com")
    signed_in = _sign_in(client, user.email)
    for bad in ("", "1234567", "x" * 201):  # 7 characters is one short
        assert _change(client, signed_in, new=bad).status_code == 422, bad
    assert client.get("/me", headers=signed_in).status_code == 200  # a refused change signs nobody out


def test_account_settings_take_only_well_formed_values(client, test_db):
    user = make_user(test_db, "profile@sessions.com")
    h = _sign_in(client, user.email)
    for bad in ({"date_of_birth": "not a date"}, {"full_name": "x" * 201}, {"full_name": {"first": "Nadia"}},
                {"gender": "robot"}, {"language": "xx"}):
        assert client.put("/profile/student", headers=h, json=bad).status_code == 422, bad

    saved = client.put("/profile/student", headers=h, json={"full_name": "Nadia Karim", "gender": "female",
                                                            "date_of_birth": "2008-03-14"}).json()
    assert (saved["full_name"], saved["gender"], saved["date_of_birth"]) == ("Nadia Karim", "female", "2008-03-14")
    saved = client.put("/profile/student", headers=h, json={"language": "bn"}).json()
    assert saved["full_name"] == "Nadia Karim" and saved["language"] == "bn"  # fields left out stay as they are
    assert client.put("/profile/student", headers=h, json={"language": None}).json()["language"] is None


def test_wrong_current_passwords_are_limited(client, test_db):
    user = make_user(test_db, "guess@sessions.com")
    h = _sign_in(client, user.email)
    for _ in range(10):
        assert _change(client, h, old="a wrong guess").status_code == 400
    res = _change(client, h)  # even the right one, until the wait is over
    assert res.status_code == 429 and "Wait 15 minutes" in res.json()["detail"]
    assert client.get("/me", headers=h).status_code == 200
