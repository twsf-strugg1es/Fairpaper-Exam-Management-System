"""The API refuses to start with a signing key short enough to guess (task 5.1): with HMAC-SHA256 tokens, a short
key can be found offline from a single token, and then any account forged."""
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _start(secret):
    env = {**os.environ, "SECRET_KEY": secret}
    return subprocess.run([sys.executable, "-c", "import app.security"], cwd=BACKEND, env=env,
                          capture_output=True, text=True, timeout=60)


def test_a_key_shorter_than_32_characters_stops_the_api():
    result = _start("x" * 31)
    assert result.returncode != 0
    assert "SECRET_KEY must be at least 32 characters" in result.stderr and "secrets.token_urlsafe" in result.stderr


def test_a_key_of_32_characters_is_enough():
    assert _start("k" * 32).returncode == 0
