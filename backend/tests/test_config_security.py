"""Production configuration guards: validate_runtime + ensure_production_safe."""

from __future__ import annotations

import base64

import pytest

from app.core.config import Settings


def _fernet_key() -> str:
    return base64.urlsafe_b64encode(b"x" * 32).decode("ascii")


def _prod_settings(**overrides) -> Settings:
    base = {
        "environment": "production",
        "secret_key": "x" * 48,
        "debug": False,
        "field_encryption_key": _fernet_key(),
        "database_url": "postgresql+psycopg://u:p@db:5432/placement",
        "seed_on_startup": False,
        "rate_limit_enabled": True,
    }
    base.update(overrides)
    return Settings(**base)


def test_valid_production_config_has_no_problems() -> None:
    assert _prod_settings().validate_runtime() == []


def test_short_secret_rejected() -> None:
    problems = _prod_settings(secret_key="short").validate_runtime()
    assert any("SECRET_KEY" in p for p in problems)


def test_dev_prefix_secret_rejected_in_production() -> None:
    problems = _prod_settings(secret_key="dev-only-insecure-key-change-me-in-production-0123456789").validate_runtime()
    assert any("SECRET_KEY" in p for p in problems)


def test_debug_rejected_in_production() -> None:
    assert any("DEBUG" in p for p in _prod_settings(debug=True).validate_runtime())


def test_missing_fernet_key_rejected() -> None:
    assert any("FIELD_ENCRYPTION_KEY" in p for p in _prod_settings(field_encryption_key="").validate_runtime())


def test_malformed_fernet_key_rejected() -> None:
    assert any("valid Fernet key" in p for p in _prod_settings(field_encryption_key="not-a-key").validate_runtime())


def test_wildcard_cors_rejected_in_production() -> None:
    assert any("CORS_ORIGINS" in p for p in _prod_settings(cors_origins=["*"]).validate_runtime())


def test_sqlite_rejected_in_production() -> None:
    assert any("sqlite" in p for p in _prod_settings(database_url="sqlite:///./x.db").validate_runtime())


def test_seed_on_startup_rejected_in_production() -> None:
    assert any("SEED_ON_STARTUP" in p for p in _prod_settings(seed_on_startup=True).validate_runtime())


def test_disabled_rate_limiting_rejected_in_production() -> None:
    assert any("RATE_LIMIT_ENABLED" in p for p in _prod_settings(rate_limit_enabled=False).validate_runtime())


def test_ensure_production_safe_raises_on_problems() -> None:
    with pytest.raises(RuntimeError):
        _prod_settings(secret_key="short").ensure_production_safe()
    # no raise for a healthy config
    _prod_settings().ensure_production_safe()


def test_non_production_environments_are_lenient() -> None:
    for env in ("development", "test"):
        s = Settings(
            environment=env,
            secret_key="x" * 32,  # the universal minimum still applies
            debug=True,
            field_encryption_key="",
            database_url="sqlite:///./dev.db",
        )
        # no production-specific complaints: no CORS/sqlite/seed/rate-limit/debug
        # objections even though every one of those is insecure-here.
        assert not any("production" in p.lower() for p in s.validate_runtime())
        s.ensure_production_safe()  # must not raise outside production