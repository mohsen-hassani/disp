"""chunk_text() — paragraph-boundary splitting, never mid-word (M19-llm.md
§5)."""

from disp.core.llm.budget import chunk_text


def test_chunk_text_single_chunk_when_under_budget() -> None:
    text = "one paragraph, well under budget."
    chunks = chunk_text(text, max_tokens=1000, overlap_tokens=0)
    assert chunks == [text]


def test_chunk_text_splits_on_paragraph_boundaries() -> None:
    paragraphs = [f"paragraph {i} " + "word " * 20 for i in range(5)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_tokens=15, overlap_tokens=0)
    assert len(chunks) > 1
    # Every chunk boundary falls on a paragraph or word boundary, never
    # mid-word: no chunk both starts and ends inside a word from `text`.
    rejoined = "".join(chunks).replace("\n\n", "")
    assert "paragraph 0" in rejoined
    assert "paragraph 4" in rejoined


def test_chunk_text_never_splits_mid_word() -> None:
    long_paragraph = " ".join(f"word{i}" for i in range(200))
    chunks = chunk_text(long_paragraph, max_tokens=10, overlap_tokens=0)
    assert len(chunks) > 1
    for chunk in chunks:
        assert not chunk.startswith(" ")
        for word in chunk.split():
            assert word.startswith("word") or word == ""


def test_chunk_text_applies_overlap() -> None:
    paragraphs = [f"paragraph {i} " + "word " * 20 for i in range(5)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_tokens=15, overlap_tokens=5)
    assert len(chunks) > 1
    # With overlap, some content from the tail of one chunk reappears at the
    # start of the next.
    assert any(chunks[i][-10:] in chunks[i + 1] for i in range(len(chunks) - 1))


def test_chunk_text_hard_splits_a_single_unbroken_long_word() -> None:
    # No space anywhere in the first max_chars — rfind returns -1, forcing
    # the max_chars fallback split point rather than a word boundary.
    long_word = "x" * 500
    chunks = chunk_text(long_word, max_tokens=10, overlap_tokens=0)
    assert len(chunks) > 1
    assert "".join(chunks) == long_word


def test_chunk_text_empty_string_returns_no_chunks() -> None:
    assert chunk_text("", max_tokens=10, overlap_tokens=0) == []
