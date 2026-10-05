"""Chunking for map-reduce callers (M19-llm.md §5).

The facade does not decide when to chunk — that is a caller's judgement,
since the reduce step is domain-specific. chunk_text() only picks split
points; a caller that must verify a chunk is actually under budget calls
LLMFacade.count_tokens() on it afterwards. The provider-accurate-count rule
(no tiktoken, no client-side estimator) governs that budget check, not the
advisory chars-per-token heuristic used here to choose where to split.
"""

# Conservative average for picking a split point only, not for any
# budget-enforcing count.
_CHARS_PER_TOKEN = 4


def chunk_text(text: str, *, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Splits on paragraph boundaries where possible, and never mid-word."""
    max_chars = max_tokens * _CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * _CHARS_PER_TOKEN

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
            tail = current[-overlap_chars:] if overlap_chars else ""
            current = f"{tail}\n\n{paragraph}" if tail else paragraph
        else:
            current = paragraph

        # A single paragraph longer than max_chars must still be split,
        # never mid-word.
        while len(current) > max_chars:
            split_at = current.rfind(" ", 0, max_chars)
            if split_at <= 0:
                split_at = max_chars
            chunks.append(current[:split_at])
            tail = current[max(0, split_at - overlap_chars) : split_at]
            current = f"{tail}{current[split_at:].lstrip(' ')}"

    if current:
        chunks.append(current)

    return chunks
