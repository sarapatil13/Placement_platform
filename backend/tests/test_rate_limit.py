"""Rate limiting: trusted-proxy identity resolution and proof limits trigger.

The app under test runs with RATE_LIMIT_ENABLED=false (see conftest), so the
route decorators are inert for the normal suite. The actual enforcement is
proven in an isolated subprocess where rate limiting is enabled with low limits.
"""

from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace

from app.core.ratelimit import client_identifier


class _FakeRequest:
    """Minimal request double exposing the bits client_identifier reads."""

    def __init__(self, peer: str, forwarded: str | None = None) -> None:
        self.client = SimpleNamespace(host=peer)
        self.headers = {"X-Forwarded-For": forwarded} if forwarded else {}


def _set_trusted(value: str) -> str:
    from app.core.config import settings

    previous = settings.rate_limit_trusted_proxy
    settings.rate_limit_trusted_proxy = value
    return previous


def test_socket_peer_used_when_no_trusted_proxy() -> None:
    previous = _set_trusted("")
    try:
        assert (
            client_identifier(_FakeRequest("203.0.113.9", forwarded="6.6.6.6"))
            == "203.0.113.9"
        )
    finally:
        _set_trusted(previous)


def test_xff_ignored_when_peer_not_trusted() -> None:
    previous = _set_trusted("192.0.2.0/24")
    try:
        assert (
            client_identifier(_FakeRequest("203.0.113.9", forwarded="6.6.6.6"))
            == "203.0.113.9"
        )
    finally:
        _set_trusted(previous)


def test_trusted_proxy_uses_leftmost_xff() -> None:
    previous = _set_trusted("203.0.113.0/24")
    try:
        assert (
            client_identifier(
                _FakeRequest("203.0.113.9", forwarded="198.51.100.7, 10.0.0.2")
            )
            == "198.51.100.7"
        )
    finally:
        _set_trusted(previous)


def test_malformed_xff_falls_back_to_peer() -> None:
    previous = _set_trusted("203.0.113.0/24")
    try:
        assert (
            client_identifier(_FakeRequest("203.0.113.9", forwarded="not-an-ip"))
            == "203.0.113.9"
        )
    finally:
        _set_trusted(previous)


def _rate_limit_script() -> str:
    return r"""
import os, sys, tempfile
from pathlib import Path

os.environ["ENVIRONMENT"] = "test"
os.environ["RATE_LIMIT_ENABLED"] = "true"
os.environ["RATE_LIMIT_DEFAULT"] = "3/minute"
os.environ["RATE_LIMIT_AUTH"] = "3/minute"
os.environ["DATABASE_URL"] = "sqlite:///" + str(
    Path(tempfile.gettempdir(), "pp_rl_test.db").as_posix()
)
os.environ["SEED_ON_STARTUP"] = "false"

from fastapi.testclient import TestClient
from app.main import app
from app.db.base import Base
from app.db.session import engine

Base.metadata.create_all(bind=engine)

with TestClient(app) as client:
    # /health falls under the default limit (3/minute): the 4th hits 429.
    codes = [client.get("/health").status_code for _ in range(5)]
    assert codes[-1] == 429, f"default limit not enforced: {codes}"

    # login falls under the auth limit (3/minute).
    codes = [
        client.post(
            "/api/v1/auth/login",
            json={"email": "acme@test.example.edu", "password": "Wrong@12345!"},
        ).status_code
        for _ in range(5)
    ]
    assert codes[-1] == 429, f"auth limit not enforced: {codes}"

print("RATE_LIMIT_OK")
"""


def test_rate_limits_actually_trigger() -> None:
    """Boot the app with rate limiting enabled and assert 429s arrive."""
    env = os.environ.copy()
    env.pop("RATE_LIMIT_ENABLED", None)
    # The command is our own interpreter plus a static script string, not input.
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _rate_limit_script()],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"subprocess failed:\n{result.stdout}\n{result.stderr}"
    assert "RATE_LIMIT_OK" in result.stdout