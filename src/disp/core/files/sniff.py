"""Magic-byte sniffing for the core file service (M18-files.md §7.1).

A *sniffable* type is identified from its leading bytes; the text family
writes no signature at all — there is no byte sequence illegal in a `.txt`
file — so text can only be *validated* as UTF-8 by FileStore.put, never
*identified* by content. Only a positively sniffed type may ever be linked
with `Content-Disposition: inline` (I6).
"""

SNIFF_HEAD_BYTES = 64

SNIFFABLE_EXTENSIONS: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}

TEXT_FAMILY_EXTENSIONS: dict[str, str] = {
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/html": ".html",
    "application/x-subrip": ".srt",
}

# Combined table used for storage-key extensions (§5) — sniffed and
# text-family types both need one, only sniffed types get one from content.
EXTENSIONS: dict[str, str] = {**SNIFFABLE_EXTENSIONS, **TEXT_FAMILY_EXTENSIONS}

TEXT_FAMILY_TYPES: frozenset[str] = frozenset(TEXT_FAMILY_EXTENSIONS)

_MAGIC_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
)

# ISO-BMFF major brands that mean "MP4 video". The `ftyp` box is shared with
# HEIC photos (heic/mif1) and M4A audio (M4A ), which must NOT sniff as
# video — hence an explicit list rather than "any ftyp".
_MP4_BRANDS: frozenset[bytes] = frozenset(
    {
        b"isom",
        b"iso2",
        b"iso3",
        b"iso4",
        b"iso5",
        b"iso6",
        b"mp41",
        b"mp42",
        b"avc1",
        b"dash",
        b"mmp4",
        b"M4V ",
        b"M4VH",
        b"M4VP",
        b"MSNV",
        b"f4v ",
    }
)
_EBML_MAGIC = b"\x1a\x45\xdf\xa3"


def sniff(head: bytes) -> str | None:
    """Identify a sniffable type from its leading bytes, or None.

    None means either "not a sniffable type at all" or "not identifiable from
    the bytes given" — callers distinguish those by checking the text-family
    table separately (sniffing can't help there; see FileStore.put).
    """
    for prefix, content_type in _MAGIC_PREFIXES:
        if head.startswith(prefix):
            return content_type
    # WebP is RIFF-framed: "RIFF" + 4 size bytes + "WEBP".
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    # ISO-BMFF: 4-byte box size, "ftyp", 4-byte major brand.
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand == b"qt  ":
            return "video/quicktime"
        if brand in _MP4_BRANDS:
            return "video/mp4"
        return None
    # EBML is shared by WebM and Matroska; only the DocType tells them apart,
    # and it sits a few dozen bytes into the header.
    if head.startswith(_EBML_MAGIC) and b"webm" in head[:SNIFF_HEAD_BYTES]:
        return "video/webm"
    return None
