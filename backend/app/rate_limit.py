"""Rate limits for the public auth endpoints: sign-in, signup and join codes.

Counts live in this process's memory, which is enough for one API instance (the pilot).
Running several instances needs a shared counter (Redis or Postgres) instead.

Per-IP limits are generous on purpose: a whole class often signs in at once from one
school or coaching-center network. The protection against password guessing is the
per-account limit on failed sign-ins.
"""
import math
import os
import threading
import time

from fastapi import HTTPException, Request, status

# (limit, window in seconds)
LOGIN_PER_IP = (100, 60)
LOGIN_FAILURES_PER_ACCOUNT = (10, 15 * 60)
PASSWORD_CHANGE_FAILURES_PER_USER = (10, 15 * 60)  # wrong current passwords in Account settings
SIGNUP_PER_IP = (60, 10 * 60)
ORG_SIGNUP_PER_IP = (10, 60 * 60)
JOIN_PER_USER = (20, 10 * 60)
RESET_REQUEST_PER_IP = (20, 10 * 60)
RESET_EMAILS_PER_ACCOUNT = (3, 60 * 60)  # beyond this, requests succeed but send nothing
RESET_CONFIRM_PER_IP = (30, 10 * 60)
VERIFY_RESEND_PER_USER = (3, 60 * 60)
INVITE_RESEND_PER_USER = (3, 60 * 60)
WAITLIST_PER_IP = (20, 10 * 60)

_MAX_KEYS = 50_000  # prune expired entries beyond this, so memory stays bounded


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self.enabled = os.getenv("RATE_LIMITS", "on").lower() != "off"

    def _recent(self, key: str, window: float, now: float) -> list[float]:
        recent = [t for t in self._hits.get(key, ()) if now - t < window]
        if recent:
            self._hits[key] = recent
        else:
            self._hits.pop(key, None)
        return recent

    def retry_after(self, key: str, rule: tuple[int, int]) -> int:
        """Seconds until `key` may act again; 0 while it's under its limit."""
        if not self.enabled:
            return 0
        limit, window = rule
        now = time.monotonic()
        with self._lock:
            recent = self._recent(key, window, now)
        return max(1, math.ceil(window - (now - recent[0]))) if len(recent) >= limit else 0

    def check(self, key: str, rule: tuple[int, int], message: str) -> None:
        """Raise 429 when `key` has used up its limit; doesn't count this request."""
        wait = self.retry_after(key, rule)
        if wait:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=message,
                headers={"Retry-After": str(wait)},
            )

    def add(self, key: str) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        with self._lock:
            self._hits.setdefault(key, []).append(now)
            if len(self._hits) > _MAX_KEYS:
                for k in list(self._hits):
                    self._recent(k, 24 * 3600, now)

    def hit(self, key: str, rule: tuple[int, int], message: str) -> None:
        self.check(key, rule, message)
        self.add(key)

    def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()

TOO_MANY = "Too many attempts. Wait a minute and try again."
TOO_MANY_INVITES = "We've sent this person 3 invites in the last hour. Try again later."


def client_ip(request: Request) -> str:
    # uvicorn --proxy-headers already resolves X-Forwarded-For from trusted proxies
    return request.client.host if request.client else "unknown"


def per_ip(name: str, rule: tuple[int, int]):
    """Dependency: count this request against the caller's IP."""
    def dependency(request: Request) -> None:
        limiter.hit(f"{name}:{client_ip(request)}", rule, TOO_MANY)
    return dependency
