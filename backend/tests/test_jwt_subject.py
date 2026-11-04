"""Tokens identify the user by ID, so an email change doesn't sign anyone out."""
import jwt

from app import models
from app.security import ALGORITHM, SECRET_KEY, create_access_token
from tests.test_organizations import make_org, make_user


def login(client, email):
    res = client.post("/token", data={"username": email, "password": "Password123!"})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def test_new_tokens_carry_the_user_id(client, test_db):
    user = make_user(test_db, "id@token.com", make_org(test_db, "Token Org"), models.ROLE_OWNER)
    claims = jwt.decode(login(client, "id@token.com"), SECRET_KEY, algorithms=[ALGORITHM])
    assert claims["sub"] == str(user.id)


def test_changing_the_email_keeps_the_session(client, test_db):
    user = make_user(test_db, "before@token.com")
    token = login(client, "before@token.com")
    user.email = "after@token.com"
    test_db.commit()
    me = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "after@token.com"


def test_tokens_from_before_the_change_still_work(client, test_db):
    make_user(test_db, "legacy@token.com")
    legacy = create_access_token({"sub": "legacy@token.com"})
    assert client.get("/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 200
    # and a refresh swaps it for an ID token
    fresh = client.post("/token/refresh", headers={"Authorization": f"Bearer {legacy}"}).json()["access_token"]
    assert "@" not in jwt.decode(fresh, SECRET_KEY, algorithms=[ALGORITHM])["sub"]


def test_unknown_or_malformed_subjects_are_rejected(client, test_db):
    for subject in ("00000000-0000-0000-0000-000000000000", "nobody@token.com", "not-an-id", ""):
        token = create_access_token({"sub": subject})
        assert client.get("/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401, subject
