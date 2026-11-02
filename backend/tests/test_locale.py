"""Organization locale (country, language, timezone, currency) and the user's own language."""
from app import models
from tests.test_organizations import headers_for, make_org, make_user


def setup(db):
    org = make_org(db, "Locale Coaching")
    owner = make_user(db, "owner@locale.com", org, models.ROLE_OWNER)
    examiner = make_user(db, "examiner@locale.com", org, models.ROLE_EXAMINER)
    student = make_user(db, "student@locale.com", org, models.ROLE_CANDIDATE)
    return org, owner, examiner, student


def test_new_organizations_default_to_utc_and_english(client, test_db):
    org, owner, _, _ = setup(test_db)
    data = client.get("/org", headers=headers_for(owner, org)).json()
    assert data["timezone"] == "UTC" and data["default_language"] == "en"
    assert data["country"] is None and data["currency"] is None


def test_org_signup_keeps_the_browser_timezone(client):
    res = client.post("/signup/organization", json={
        "email": "head@dhaka.edu", "password": "Str0ng-pass!", "organization_name": "Dhaka Prep",
        "timezone": "Asia/Dhaka", "country": "bd",
    })
    assert res.status_code == 201, res.text
    membership = res.json()["memberships"][0]
    assert membership["timezone"] == "Asia/Dhaka" and membership["default_language"] == "en"


def test_manager_changes_locale_one_field_at_a_time(client, test_db):
    org, owner, _, _ = setup(test_db)
    h = headers_for(owner, org)
    res = client.patch("/org", headers=h, json={"timezone": "Asia/Dhaka", "country": "bd", "currency": "bdt", "default_language": "bn"})
    assert res.status_code == 200, res.text
    assert res.json()["country"] == "BD" and res.json()["currency"] == "BDT"

    # A rename leaves the locale alone
    res = client.patch("/org", headers=h, json={"name": "Renamed Coaching"})
    assert res.json()["name"] == "Renamed Coaching" and res.json()["timezone"] == "Asia/Dhaka"

    # Empty country/currency clear them; the required fields can't be cleared
    res = client.patch("/org", headers=h, json={"country": "", "currency": "", "timezone": None})
    assert res.json()["country"] is None and res.json()["currency"] is None
    assert res.json()["timezone"] == "Asia/Dhaka"

    # Members see the organization's timezone in /me
    me = client.get("/me", headers=h).json()
    assert me["memberships"][0]["timezone"] == "Asia/Dhaka" and me["memberships"][0]["default_language"] == "bn"


def test_locale_values_are_validated(client, test_db):
    org, owner, _, _ = setup(test_db)
    h = headers_for(owner, org)
    for body in ({"timezone": "Mars/Olympus"}, {"country": "BGD"}, {"currency": "TK"}, {"default_language": "xx"}):
        assert client.patch("/org", headers=h, json=body).status_code == 422, body


def test_only_managers_change_locale(client, test_db):
    org, _, examiner, student = setup(test_db)
    for member in (examiner, student):
        assert client.patch("/org", headers=headers_for(member, org), json={"timezone": "Asia/Dhaka"}).status_code == 403


def test_another_organization_cannot_change_it(client, test_db):
    org, _, _, _ = setup(test_db)
    other = make_org(test_db, "Other Coaching")
    outsider = make_user(test_db, "owner@other.com", other, models.ROLE_OWNER)
    res = client.patch("/org", headers=headers_for(outsider, org), json={"timezone": "Asia/Dhaka"})
    assert res.status_code == 403
    test_db.refresh(org)
    assert org.timezone == "UTC"


def test_user_picks_a_language_or_falls_back_to_the_organization(client, test_db):
    org, _, _, student = setup(test_db)
    h = headers_for(student, org)
    res = client.put("/profile/student", headers=h, json={"language": "bn"})
    assert res.status_code == 200 and res.json()["language"] == "bn"
    assert client.get("/me", headers=h).json()["language"] == "bn"

    assert client.put("/profile/student", headers=h, json={"language": "klingon"}).status_code == 422

    res = client.put("/profile/student", headers=h, json={"language": None})
    assert res.json()["language"] is None
