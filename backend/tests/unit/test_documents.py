"""Reading a saved document, and refusing clearly when it cannot be read."""

import io

import pytest

from app.ingestion.deterministic import parse
from app.ingestion.documents import MAX_BYTES, UnsupportedDocumentError, extract_text

LISTING_LINES = [
    "88 Marlow Avenue, Toronto",
    "Offered at $1,149,000",
    "Bedrooms: 4",
    "Bathrooms: 2.5",
    "Approx Sq Ft: 1850",
    "Built in 1991",
    "Taxes: $6,412.00 / 2025",
]


def make_pdf(lines: list[str]) -> bytes:
    """A minimal PDF with a real text layer, as a browser's Save-as-PDF produces."""
    drawn = "\n".join(f"({line}) Tj 0 -20 Td" for line in lines)
    content = f"BT /F1 12 Tf 50 750 Td {drawn} ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


class TestPdf:
    def test_a_printed_listing_reads_exactly(self):
        """A browser's PDF carries a real text layer, so the values are lifted
        rather than inferred — and can be shown back as the characters they were."""
        text = extract_text(make_pdf(LISTING_LINES), "application/pdf", filename="l.pdf")
        fields = parse(text).fields
        assert fields["listing_price"] == 1_149_000
        assert fields["bedrooms"] == 4
        assert fields["bathrooms"] == 2.5
        assert fields["square_feet"] == 1850
        assert fields["year_built"] == 1991
        assert fields["annual_property_tax"] == 6412

    def test_a_pdf_with_no_text_layer_explains_the_difference(self):
        """A scan or an exported image has no text. Saying "printing works,
        scanning does not" is more use than "no text found"."""
        with pytest.raises(UnsupportedDocumentError, match="no text layer"):
            extract_text(make_pdf([]), "application/pdf", filename="scan.pdf")

    def test_a_file_that_is_not_a_pdf_is_refused(self):
        with pytest.raises(UnsupportedDocumentError, match="could not be opened"):
            extract_text(b"not a pdf at all", "application/pdf", filename="x.pdf")

    def test_it_reads_by_extension_when_the_type_is_missing(self):
        text = extract_text(make_pdf(LISTING_LINES), "", filename="listing.pdf")
        assert "Marlow" in text


class TestOtherTypes:
    def test_plain_text_passes_straight_through(self):
        assert "Offered at" in extract_text(b"Offered at $849,000", "text/plain")

    def test_an_image_says_what_it_would_need(self):
        """A screenshot has no text layer. Rather than half-support it with a
        guess, say what it would take and point at the path that works today."""
        with pytest.raises(UnsupportedDocumentError) as excinfo:
            extract_text(b"\x89PNG\r\n", "image/png", filename="shot.png")
        message = str(excinfo.value)
        assert "no text layer" in message
        assert "Save as PDF" in message

    def test_an_unknown_type_is_refused_by_name(self):
        with pytest.raises(UnsupportedDocumentError, match="not something we can read"):
            extract_text(b"data", "application/zip", filename="x.zip")


class TestLimits:
    def test_an_empty_file_is_refused(self):
        with pytest.raises(UnsupportedDocumentError, match="empty"):
            extract_text(b"", "application/pdf")

    def test_an_oversized_file_is_refused_with_both_numbers(self):
        with pytest.raises(UnsupportedDocumentError) as excinfo:
            extract_text(b"x" * (MAX_BYTES + 1), "application/pdf")
        assert "the limit is" in str(excinfo.value)
