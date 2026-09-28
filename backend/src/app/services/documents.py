"""Document text and metadata extraction (PDF via PyMuPDF, DOCX via python-docx).

Fails safe: any unreadable file raises `DocumentParseError` with a clean message
rather than propagating a library exception into the API layer.

Extraction is bounded: oversized decompressed content (DOCX is a zip), large
page counts, and excessive extracted text are rejected so a hostile document
cannot exhaust memory or CPU.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

from app.core.config import settings
from app.core.errors import ValidationError as _ValidationError


class DocumentParseError(_ValidationError):
    pass


SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt")


def extract_text_from_bytes(data: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(data)
    if suffix == ".docx":
        return _extract_docx(data)
    if suffix == ".txt":
        return _extract_text(data)
    raise DocumentParseError(f"Unsupported document type: '{suffix}'.")


def _enforce_text_limit(text: str) -> str:
    if len(text) > settings.max_extracted_text_chars:
        raise DocumentParseError(
            "Document text exceeds the extraction size limit.",
            code="document_too_large",
        )
    return text


def _extract_text(data: bytes) -> str:
    try:
        text = data.decode("utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise DocumentParseError("The text file is not valid UTF-8.") from exc
    if not text:
        raise DocumentParseError("The text file is empty.")
    return _enforce_text_limit(text)


def _extract_pdf(data: bytes) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise DocumentParseError("PDF support is unavailable on this server.") from exc
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        if doc.page_count > settings.max_pdf_pages:
            doc.close()
            raise DocumentParseError(
                f"PDF has more than {settings.max_pdf_pages} pages.",
                code="document_too_large",
            )
        chunks: list[str] = []
        total = 0
        limit = settings.max_extracted_text_chars
        for page in doc:
            text = page.get_text("text")
            total += len(text)
            if total > limit:
                doc.close()
                raise DocumentParseError(
                    "Document text exceeds the extraction size limit.",
                    code="document_too_large",
                )
            chunks.append(text)
        doc.close()
        text = "\n".join(chunks)
    except DocumentParseError:
        raise
    except Exception as exc:
        raise DocumentParseError(f"Could not read PDF: {exc}") from exc
    if not text.strip():
        raise DocumentParseError("The PDF contains no extractable text (scanned/image-only?).")
    return _enforce_text_limit(text)


def _extract_docx(data: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover
        raise DocumentParseError("DOCX support is unavailable on this server.") from exc

    # DOCX is a zip: reject clearly bombed archives before any XML is parsed by
    # inspecting the summed uncompressed sizes of the entries we will touch.
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            total_uncompressed = sum(
                info.file_size for info in zf.infolist() if not info.is_dir()
            )
    except zipfile.BadZipFile as exc:
        raise DocumentParseError("The DOCX is not a valid zip archive.") from exc
    if total_uncompressed > settings.max_docx_decompressed_bytes:
        raise DocumentParseError(
            "DOCX contains compressed content that exceeds the size limit.",
            code="document_too_large",
        )

    try:
        doc = Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        tables = []
        for table in doc.tables:
            for row in table.rows:
                tables.append(" | ".join(cell.text for cell in row.cells))
        text = "\n".join([p for p in parts if p.strip()] + tables)
    except DocumentParseError:
        raise
    except Exception as exc:
        raise DocumentParseError(f"Could not read DOCX: {exc}") from exc
    if not text.strip():
        raise DocumentParseError("The DOCX contains no extractable text.")
    return _enforce_text_limit(text)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_storage_name(original: str, digest: str) -> str:
    """Neutralises the user-supplied filename before it touches the disk."""
    import re

    base = Path(original).name
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return f"{digest[:16]}_{base}"