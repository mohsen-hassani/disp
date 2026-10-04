"""Magic-byte sniffing for the core file/asset service (M18-files.md §7.1).

Ported from plants/config.py's image-sniffing table, extended with PDF and a
text-family list for formats that write no signature at all — there is no
byte sequence illegal in a `.txt` file, so text can only be *validated* as
UTF-8 by FileStore.put, never *identified* by content (I5/I6 in
docs/milestones/server/M18-files.md §2 — only a positively sniffed type may ever
be served inline).
"""

SNIFFABLE_EXTENSIONS: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
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


def sniff(head: bytes) -> str | None:
    """Identify a sniffable type from its leading bytes, or None.

    None means either "not a sniffable type at all" or "not identifiable from
    the bytes given" — callers distinguish those by checking the text-family
    table separately (sniffing can't help there; see FileStore.put).
    """
    for prefix, content_type in _MAGIC_PREFIXES:
        if head.startswith(prefix):
            return content_type
    # WebP is RIFF-framed: "RIFF" + 4 size bytes + "WEBP". Needs 12 bytes,
    # comfortably inside the 16-byte sniff buffer FileStore.put uses.
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None
