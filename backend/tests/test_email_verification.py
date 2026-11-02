"""Soft email verification: signup sends a link, the link confirms, nothing is blocked."""
import re
from datetime import datetime, timedelta, timezone

import jwt

from app import models, notify
from app.routers.email_verification import make_token
from app.security import ALGORITHM, SECRET_KEY, create_access_token
from tests.test_organizations import headers_for, make_user


def setup_function():
    notify.outbox.clear()


def link_token():
    match = re.search(r"/verify-email/([\w.-]+)", notify.outbox[-1].text)
    assert match, notify.outbox[-1].text
    return match.group(1)


def verify(client, token):
    return client.post("/verify-email", json={"token": token})


def test_signup_sends_a_link_that_confirms_the_address(client, test_db):
    res = client.post("/signup", json={"email": "new@verify.com", "password": "Str0ng-pass!"})
    assert res.status_code == 201 and res.json()["email_verified_at"] is None
    assert notify.outbox[-1].to == "new@verify.com"

    res = verify(client, link_token())
    assert res.status_code == 200
    user = test_db.query(models.User).filter_by(email="new@verify.com").one()
    assert user.email_verified_at is not None
    assert verify(client, link_token()).status_code == 200  # clicking twice is fine


def test_org_signup_sends_a_link_too(client):
    client.post("/signup/organization", json={"email": "head@verify.com", "password": "Str0ng-pass!", "organization_name": "Verify Prep"})
    assert notify.outbox[-1].to == "head@verify.com"


def test_unverified_accounts_still_work(client, test_db):
    client.post("/signup", json={"email": "later@verify.com", "password": "Str0ng-pass!"})
    token = client.post("/token", data={"username": "later@verify.com", "password": "Str0ng-pass!"}).json()["access_token"]
    me = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email_verified_at"] is None


def test_a_link_for_an_old_email_no_longer_works(client, test_db):
    user = make_user(test_db, "old@verify.com")
    token = make_token(user)
    user.email = "new-address@verify.com"
    test_db.commit()
    assert verify(client, token).status_code == 400


def test_sign_in_tokens_and_forged_links_are_refused(client, test_db):
    user = make_user(test_db, "forge@verify.com")
    assert verify(client, create_access_token({"sub": str(user.id)})).status_code == 400
    forged = jwt.encode({"sub": str(user.id), "email": user.email, "purpose": "verify-email",
                         "exp": datetime.now(timezone.utc) + timedelta(days=1)}, "wrong-key", algorithm=ALGORITHM)
    assert verify(client, forged).status_code == 400
    expired = jwt.encode({"sub": str(user.id), "email": user.email, "purpose": "verify-email",
                          "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}, SECRET_KEY, algorithm=ALGORITHM)
    assert verify(client, expired).status_code == 400
    assert verify(client, "x" * 40).status_code == 400


def test_resend_is_for_the_signed_in_user_and_capped(client, test_db):
    user = make_user(test_db, "resend@verify.com")
    h = headers_for(user)
    for _ in range(3):
        assert client.post("/verify-email/resend", headers=h).status_code == 200
    assert client.post("/verify-email/resend", headers=h).status_code == 429
    assert [e.to for e in notify.outbox] == ["resend@verify.com"] * 3
    assert client.post("/verify-email/resend").status_code == 401


def test_resend_does_nothing_once_confirmed(client, test_db):
    user = make_user(test_db, "done@verify.com")
    user.email_verified_at = datetime.now(timezone.utc)
    test_db.commit()
    res = client.post("/verify-email/resend", headers=headers_for(user))
    assert res.status_code == 200 and notify.outbox == []


def test_a_password_reset_also_confirms_the_address(client, test_db):
    make_user(test_db, "reset@verify.com")
    client.post("/password-reset/request", json={"email": "reset@verify.com"})
    token = re.search(r"/reset-password/([\w-]+)", notify.outbox[-1].text).group(1)
    client.post("/password-reset/confirm", json={"token": token, "new_password": "N3w-password!"})
    assert test_db.query(models.User).filter_by(email="reset@verify.com").one().email_verified_at is not None


def test_a_confirmation_link_is_not_a_sign_in_token(client, test_db):
    user = make_user(test_db, "notasession@verify.com")
    assert client.get("/me", headers={"Authorization": f"Bearer {make_token(user)}"}).status_code == 401
