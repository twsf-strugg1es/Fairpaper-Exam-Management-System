"""Error reports to Sentry (task 5.5): off without a DSN, never personal data, and every report says who and where."""
from app import error_tracking
from app.logging_config import bind_log_context


def test_reporting_is_off_without_a_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    started = []
    monkeypatch.setattr(error_tracking.sentry_sdk, "init", lambda **kw: started.append(kw))
    assert error_tracking.init_error_tracking() is False and started == []


def test_with_a_dsn_it_starts_without_personal_data(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://key@o1.ingest.de.sentry.io/1")
    started = []
    monkeypatch.setattr(error_tracking.sentry_sdk, "init", lambda **kw: started.append(kw))
    assert error_tracking.init_error_tracking() is True
    assert started[0]["dsn"].endswith("/1") and started[0]["send_default_pii"] is False


def test_requests_tag_reports_with_ids_only(monkeypatch):
    users, tags = [], {}
    monkeypatch.setattr(error_tracking.sentry_sdk, "set_user", users.append)
    monkeypatch.setattr(error_tracking.sentry_sdk, "set_tag", tags.__setitem__)
    bind_log_context(user_id="u-1", organization_id="o-1", role="owner")
    assert users == [{"id": "u-1"}] and tags == {"organization_id": "o-1", "role": "owner"}
