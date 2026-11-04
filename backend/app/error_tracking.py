"""Error reports to Sentry (task 5.5).

Off unless SENTRY_DSN is set. Reports carry the user's and organization's ids and the role, never emails, names,
IP addresses or request bodies (`send_default_pii` stays off), so an answer or a password can't end up in Sentry.
"""
import os

import sentry_sdk


def init_error_tracking() -> bool:
    """Start reporting when SENTRY_DSN is set; returns whether it did."""
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        send_default_pii=False,
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0")),
    )
    return True


def tag_request(user_id: str | None = None, organization_id: str | None = None, role: str | None = None, **_) -> None:
    """Who and where, for any error this request reports. Does nothing when reporting is off."""
    if user_id:
        sentry_sdk.set_user({"id": user_id})
    if organization_id:
        sentry_sdk.set_tag("organization_id", organization_id)
    if role:
        sentry_sdk.set_tag("role", role)
