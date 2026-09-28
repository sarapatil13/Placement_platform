"""Security regression tests: upload pre-checks, document extraction limits,
security headers, and the OpenAPI docs toggle."""

from __future__ import annotations

import io
import zipfile

import pytest
from tests.conftest import TestData, auth_headers

from app.api.deps import enforce_request_content_length
from app.core.config import Settings, settings
from app.core.errors import PayloadTooLargeError
from app.core.ratelimit import route_limit
from app.services.documents import DocumentParseError, extract_text_from_bytes


class _FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


def _declared(megabytes: float) -> _FakeRequest:
    return _FakeRequest({"Content-Length": str(int(megabytes * 1024 * 1024))})


def test_size_precheck_accepts_small_body() -> None:
    enforce_request_content_length(_declared(4.9), max_bytes=settings.max_upload_bytes)  # no raise


def test_size_precheck_accepts_max_size_with_overhead_slack() -> None:
    # a file at the exact limit plus multipart overhead stays under limit+slack
    enforce_request_content_length(_declared(5.5), max_bytes=settings.max_upload_bytes)


def test_size_precheck_rejects_obviously_oversized_body() -> None:
    with pytest.raises(PayloadTooLargeError):
        enforce_request_content_length(_declared(8.0), max_bytes=settings.max_upload_bytes)


def test_size_precheck_ignores_garbage_header() -> None:
    enforce_request_content_length(_FakeRequest({"Content-Length": "banana"}), max_bytes=(5 << 20))  # no raise


def test_oversized_multipart_upload_rejected_413(seed: TestData, client) -> None:
    token, _student = seed.student()
    resp = client.post(
        "/api/v1/resumes",
        files={"file": ("huge.pdf", b"x" * (8 * 1024 * 1024), "application/pdf")},
        headers=auth_headers(token),
    )
    assert resp.status_code == 413
    assert resp.json()["code"] == "upload_too_large"


def test_oversized_txt_rejected() -> None:
    blob = ("x" * (settings.max_extracted_text_chars + 1)).encode()
    with pytest.raises(DocumentParseError):
        extract_text_from_bytes(blob, "big.txt")


def test_zip_bomb_docx_rejected() -> None:
    buf = io.BytesIO()
    big = b"0" * (settings.max_docx_decompressed_bytes + 1)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", big)
    with pytest.raises(DocumentParseError):
        extract_text_from_bytes(buf.getvalue(), "bomb.docx")


def test_too_many_pdf_pages_rejected() -> None:
    import fitz  # PyMuPDF

    doc = fitz.open()
    for _ in range(settings.max_pdf_pages + 1):
        doc.new_page()
    data = doc.tobytes()
    doc.close()
    with pytest.raises(DocumentParseError):
        extract_text_from_bytes(data, "many.pdf")


def test_fixed_security_headers_present(client) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert "permissions-policy" in resp.headers
    assert resp.headers["x-request-id"]


def test_hsts_only_when_strict_transport() -> None:
    from app.main import security_headers

    assert "Strict-Transport-Security" not in security_headers(strict_transport=False)
    assert "Strict-Transport-Security" in security_headers(strict_transport=True)


def test_docs_enabled_only_outside_production() -> None:
    assert settings.docs_enabled is True  # test environment
    assert (
        Settings(environment="production", api_docs_enable_production=False).docs_enabled
        is False
    )
    assert (
        Settings(environment="production", api_docs_enable_production=True).docs_enabled
        is True
    )


def test_route_limit_is_inert_when_disabled() -> None:
    # RATE_LIMIT_ENABLED=false in tests: decorators must pass through untouched
    def endpoint():
        """docstring preserved"""

    decorated = route_limit("1/minute")(endpoint)
    assert decorated is endpoint
    assert decorated.__name__ == "endpoint"