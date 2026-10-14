"""Application configuration.

All institution-specific *policy* (branding, grading scale, allowed departments)
is configuration, not business logic. Business logic reads these settings so a
second university can be onboarded without code changes.
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _is_valid_fernet_key(value: str) -> bool:
    """True when the value is a well-formed urlsafe-base64 32-byte Fernet key."""
    if len(value) != 44:
        return False
    try:
        return len(base64.urlsafe_b64decode(value.encode("ascii"))) == 32
    except (ValueError, UnicodeEncodeError):
        return False

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class InstitutionSettings(BaseSettings):
    """Institution-scoped configuration. Override via env or .env file."""

    model_config = SettingsConfigDict(
        env_prefix="INSTITUTION_", env_file=".env", extra="ignore"
    )

    name: str = "KLE Technological University"
    short_name: str = "KLE Tech"
    code: str = "KLE"
    city: str = "Hubballi, Karnataka, India"
    # The university identity is embedded in issued JWTs; changing it invalidates sessions.
    identity_issuer: str = "placement-platform"
    grading_scale_max: float = 10.0
    # Backlog handling vocabulary, institution-controlled.
    backlog_statuses_counted_as_active: list[str] = Field(
        default_factory=lambda: ["active", "cleared_in_semester", "not_cleared"]
    )
    contact_email: str = "placementcell@kletech.example.edu"
    # Set false only in local dev with synthetic data.
    allow_self_registration: bool = True
    data_processing_notice: str = (
        "Academic records on this platform are maintained by the university placement "
        "cell. Students may edit contact details and non-authoritative profile fields; "
        "College ID, department, batch, CGPA and backlog records are institution-owned "
        "and can only be corrected by placement cell staff."
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- app ---
    app_name: str = "Student Placement Navigation Platform"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"

    # --- server ---
    host: str = "127.0.0.1"
    port: int = 8000

    # --- database ---
    # SQLite by default for local dev; PostgreSQL in production via DATABASE_URL.
    database_url: str = Field(
        default="sqlite:///./placement.db",
        description="SQLAlchemy URL. Use postgresql+psycopg://... in production.",
    )
    database_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # --- security ---
    secret_key: str = "dev-only-insecure-key-change-me-in-production-0123456789"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 14
    password_min_length: int = 10
    bcrypt_rounds: int = 12

    # Fernet key for encrypting sensitive columns at rest. Empty disables encryption,
    # which is only acceptable for local dev with synthetic data.
    field_encryption_key: str = ""

    # --- cors ---
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    cors_allow_credentials: bool = True

    # --- uploads ---
    upload_dir: Path = Field(default_factory=lambda: BACKEND_DIR / "storage" / "uploads")
    max_upload_bytes: int = 5 * 1024 * 1024
    allowed_resume_mime: list[str] = Field(
        default_factory=lambda: [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]
    )
    allowed_resume_ext: list[str] = Field(default_factory=lambda: [".pdf", ".docx"])
    allowed_jd_mime: list[str] = Field(
        default_factory=lambda: [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
        ]
    )

    # --- rate limiting ---
    rate_limit_enabled: bool = True
    rate_limit_default: str = "120/minute"
    rate_limit_auth: str = "10/minute"
    rate_limit_write: str = "40/minute"
    rate_limit_upload: str = "15/minute"
    rate_limit_ai: str = "20/minute"
    # Comma-separated IPs/CIDRs allowed to forward `X-Forwarded-For`. Empty
    # means the header is never trusted and the socket peer address is used.
    # Trusting arbitrary client-supplied forwarding headers would let users
    # spoof their rate-limit identity, so this must be an explicit opt-in for
    # reverse-proxy deployments (e.g. TRUSTED_PROXY=10.0.0.5 or 10.0.0.0/8).
    rate_limit_trusted_proxy: str = ""

    # --- document extraction limits ---
    # Defense-in-depth against decompression bombs: uploads are capped by size,
    # and extraction additionally caps what is actually parsed/held in memory.
    max_extracted_text_chars: int = 200_000
    max_pdf_pages: int = 100
    max_docx_decompressed_bytes: int = 30 * 1024 * 1024

    # --- api docs ---
    # Swagger/Redoc/OpenAPI are always served outside production; in production
    # they are only exposed when explicitly opted in.
    api_docs_enable_production: bool = False

    # --- bulk import guard ---
    max_import_rows: int = 500

    # --- ai ---
    ai_provider: Literal["heuristic", "openai_compatible", "anthropic", "local"] = (
        "heuristic"
    )
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_timeout_seconds: float = 30.0
    ai_max_retries: int = 2
    ai_enabled: bool = True

    # --- institution ---
    institution: InstitutionSettings = Field(default_factory=InstitutionSettings)

    # --- misc ---
    seed_on_startup: bool = False
    pagination_default_limit: int = 25
    pagination_max_limit: int = 200

    # --- seeding credentials (dev/test only) ---
    # Optional overrides for the demo seeder. When unset, the seeder generates
    # a random password during seeding and prints it for the first run. Seeding
    # is refused entirely in production regardless of these values.
    seed_admin_email: str = "admin@kletech.example.edu"
    seed_admin_password: str = ""
    seed_student_password: str = ""

    @field_validator("cors_origins", "allowed_resume_mime", "allowed_resume_ext", mode="before")
    @classmethod
    def _split_csv(cls, v: Any) -> Any:
        """Accept JSON arrays or comma-separated strings for list settings."""
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                try:
                    return json.loads(s)
                except json.JSONDecodeError:
                    pass
            return [item.strip() for item in s.split(",") if item.strip()]
        return v

    @field_validator("upload_dir", mode="before")
    @classmethod
    def _expand(cls, v: Any) -> Any:
        return Path(v).expanduser() if isinstance(v, str) else v

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def docs_enabled(self) -> bool:
        """OpenAPI docs are always on in dev/test; opted-in in production."""
        return self.api_docs_enable_production or not self.is_production

    @property
    def trusted_proxy_networks(self) -> list[Any]:
        """Parsed trusted-proxy networks. Defaults to [] (never trust XFF)."""
        import ipaddress

        networks: list[Any] = []
        for raw in (p for p in self.rate_limit_trusted_proxy.split(",") if p.strip()):
            try:
                networks.append(ipaddress.ip_network(raw.strip(), strict=False))
            except ValueError:
                continue
        return networks

    def validate_runtime(self) -> list[str]:
        """Return a list of configuration problems. Empty list means healthy."""
        problems: list[str] = []
        if len(self.secret_key) < 32:
            problems.append("SECRET_KEY is shorter than 32 characters")
        if self.is_production:
            if self.secret_key.startswith("dev-only") or len(self.secret_key) < 32:
                problems.append("SECRET_KEY must be set to a strong random value in production")
            if not self.field_encryption_key:
                problems.append("FIELD_ENCRYPTION_KEY is required in production")
            elif not _is_valid_fernet_key(self.field_encryption_key):
                problems.append(
                    "FIELD_ENCRYPTION_KEY must be a valid Fernet key "
                    "(urlsafe base64, 32 bytes)"
                )
            if self.debug:
                problems.append("DEBUG must be false in production")
            if "*" in self.cors_origins:
                problems.append("CORS_ORIGINS must not contain '*' in production")
            if self.is_sqlite:
                problems.append(
                    "DATABASE_URL must use PostgreSQL (sqlite is not allowed in production)"
                )
            if self.seed_on_startup:
                problems.append("SEED_ON_STARTUP must be false in production")
            if not self.rate_limit_enabled:
                problems.append("RATE_LIMIT_ENABLED must be true in production")
        return problems

    def ensure_production_safe(self) -> None:
        """Raise RuntimeError when production configuration is invalid so a
        misconfigured server fails fast at startup instead of silently running
        with insecure defaults."""
        problems = self.validate_runtime()
        if problems:
            raise RuntimeError(
                "Refusing to start with an invalid production configuration: "
                + "; ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
