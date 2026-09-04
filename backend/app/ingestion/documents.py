"""Getting text out of a document the user already has.

The workflow this exists for: open the listing in your own browser, print it to
PDF, drop the file here. Two clicks, no copying, and — unlike having the product
fetch the page — nothing that any site's terms have an opinion about. The user
viewed a page they were entitled to view and saved what they saw.

A browser's "Save as PDF" produces a real text layer, so extraction is exact and
needs no OCR, no model and no network. That matters beyond convenience: text
lifted from a PDF can be shown back to the user as the characters it came from,
which a model's reading of a picture cannot be.

Images are a different problem. A screenshot has no text layer, so it needs OCR or
a vision model, and neither is assumed to exist here. Rather than half-support it,
:func:`extract_text` says plainly what a PNG would need.
"""

from __future__ import annotations

import io

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 20

PDF_TYPES = {"application/pdf"}
TEXT_TYPES = {"text/plain", "text/html", "text/markdown"}
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


class UnsupportedDocumentError(ValueError):
    """The document cannot be read, with a reason the user can act on."""


def extract_text(content: bytes, media_type: str, *, filename: str = "") -> str:
    """Text from a PDF or a text file, or a refusal that explains itself."""
    if not content:
        raise UnsupportedDocumentError("That file is empty.")
    if len(content) > MAX_BYTES:
        raise UnsupportedDocumentError(
            f"That file is {len(content) / 1_000_000:.1f} MB; the limit is "
            f"{MAX_BYTES // 1_000_000} MB. A listing printed to PDF is usually well under it."
        )

    media_type = (media_type or "").split(";")[0].strip().lower()
    if media_type in PDF_TYPES or filename.lower().endswith(".pdf"):
        return _from_pdf(content)
    if media_type in TEXT_TYPES or filename.lower().endswith((".txt", ".md")):
        return content.decode("utf-8", errors="replace")
    if media_type in IMAGE_TYPES:
        raise UnsupportedDocumentError(
            "A screenshot has no text layer, so reading it needs optical character "
            "recognition or a vision model, neither of which is configured. Print the "
            "listing to PDF instead (Ctrl+P, then Save as PDF) and upload that — the "
            "text comes out exactly rather than being guessed at."
        )
    raise UnsupportedDocumentError(
        f"{media_type or 'That file type'} is not something we can read. Upload a PDF, "
        "or paste the listing text."
    )


def _from_pdf(content: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(content))
    except PdfReadError as exc:
        raise UnsupportedDocumentError(f"That PDF could not be opened: {exc}") from exc

    if reader.is_encrypted:
        raise UnsupportedDocumentError(
            "That PDF is password protected. Save an unprotected copy and try again."
        )

    pages = reader.pages[:MAX_PAGES]
    text = "\n".join(page.extract_text() or "" for page in pages)
    if not text.strip():
        raise UnsupportedDocumentError(
            "That PDF has no text layer — it is probably a scan or an exported image. "
            "Printing the listing page to PDF from your browser produces real text; "
            "photographing or scanning it does not."
        )
    return text
