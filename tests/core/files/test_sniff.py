"""Magic-byte sniffing table (M18-files.md §7.1)."""

from disp.core.files.sniff import TEXT_FAMILY_TYPES, sniff


def test_sniffs_jpeg() -> None:
    assert sniff(b"\xff\xd8\xff\xe0" + b"\x00" * 12) == "image/jpeg"


def test_sniffs_png() -> None:
    assert sniff(b"\x89PNG\r\n\x1a\n") == "image/png"


def test_sniffs_gif87a() -> None:
    assert sniff(b"GIF87a") == "image/gif"


def test_sniffs_gif89a() -> None:
    assert sniff(b"GIF89a") == "image/gif"


def test_sniffs_pdf() -> None:
    assert sniff(b"%PDF-1.4") == "application/pdf"


def test_sniffs_webp_riff_special_case() -> None:
    head = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP"
    assert sniff(head) == "image/webp"


def test_unrecognized_bytes_return_none() -> None:
    assert sniff(b"not a real file, just plain text") is None


def test_riff_without_webp_marker_returns_none() -> None:
    assert sniff(b"RIFF\x00\x00\x00\x00AVI ") is None


def test_svg_is_not_sniffable() -> None:
    # Unsniffable by design (I6) — XML text carries no magic bytes, which is
    # what makes storing it safe: it can never be served inline.
    assert sniff(b"<?xml version='1.0'?><svg></svg>") is None


def test_text_family_types_are_not_in_the_sniffable_table() -> None:
    for content_type in TEXT_FAMILY_TYPES:
        # Any byte sequence handed to sniff() for a text-family payload must
        # never accidentally match a magic prefix.
        assert sniff(content_type.encode()) is None
