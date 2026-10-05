"""Request types and language-code normalisation (M22-translation.md §6)."""

from disp.core.translation.schema import (
    DetectRequest,
    Feature,
    TranslateRequest,
    normalize_lang,
)


def test_normalize_lang_upcases_and_dashes() -> None:
    assert normalize_lang("de") == "DE"
    assert normalize_lang("pt_br") == "PT-BR"
    assert normalize_lang("  en-gb  ") == "EN-GB"


def test_normalize_lang_strips_stray_punctuation() -> None:
    assert normalize_lang("de;drop") == "DEDROP"
    assert normalize_lang("") == ""


def test_normalize_lang_does_not_rewrite_deprecated_en() -> None:
    """§6: rewriting DeepL's deprecated `EN` target to `EN-US` would pick a
    dialect on the caller's behalf, giving someone who meant `EN-GB` American
    spelling with no indication of why. Normalisation only — never repair."""
    assert normalize_lang("en") == "EN"


def test_char_count_is_source_characters() -> None:
    req = TranslateRequest(texts=("abc", "de"), target_lang="DE")
    assert req.char_count == 5
    assert DetectRequest(texts=("abcde",)).char_count == 5


def test_feature_values_are_stable() -> None:
    # These strings reach no database column, but they do reach
    # TranslationNotSupported's message and backend `supports` sets.
    assert {f.value for f in Feature} == {"translate", "detect", "formality"}
