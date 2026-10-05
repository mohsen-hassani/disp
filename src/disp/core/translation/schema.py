"""Request and result types for disp.core.translation (M22-translation.md §4, §6).

Frozen dataclasses rather than Pydantic models: nothing here crosses an HTTP
boundary (§10 — the service has no routes), so there is no serialisation or
validation surface to pay for. `texts` is a tuple so a request is genuinely
hashable and cannot be mutated between the build and the parse halves of a
backend call (§4).
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

# Anything that is not a letter, digit or separator. Deliberately permissive:
# §6 argues the facade must normalise codes but MUST NOT validate them against
# a table, because a hardcoded language list goes stale the week a provider
# adds a language and differs per provider anyway.
_LANG_STRIP_RE = re.compile(r"[^A-Za-z0-9_-]")

Formality = Literal["default", "less", "more"]


class Feature(StrEnum):
    """A capability a backend either has or does not. Declared on the backend
    as `supports`, and enforced by the backend raising TranslationNotSupported
    (T4) — `supports` is advisory metadata for callers that want to ask first,
    never the only gate."""

    TRANSLATE = "translate"
    DETECT = "detect"
    FORMALITY = "formality"


def normalize_lang(code: str) -> str:
    """Upper-case, `_`-to-`-`, whitespace and stray punctuation removed.

    Normalisation only — an unrecognised code is the provider's error to raise
    (surfaced as TranslationRejected), not ours to pre-empt (§6). In
    particular this does NOT rewrite DeepL's deprecated `EN` target to
    `EN-US`: picking a dialect on the caller's behalf gives someone who meant
    `EN-GB` American spelling with no indication of why.
    """
    return _LANG_STRIP_RE.sub("", code.strip()).replace("_", "-").upper()


@dataclass(frozen=True)
class TranslateRequest:
    texts: tuple[str, ...]
    target_lang: str
    source_lang: str | None = None
    formality: Formality | None = None

    @property
    def char_count(self) -> int:
        """Source characters — the unit every provider meters (§7)."""
        return sum(len(text) for text in self.texts)


@dataclass(frozen=True)
class DetectRequest:
    texts: tuple[str, ...]

    @property
    def char_count(self) -> int:
        return sum(len(text) for text in self.texts)


@dataclass(frozen=True)
class Translated:
    text: str
    detected_source_lang: str | None = None


@dataclass(frozen=True)
class Detected:
    lang: str
    confidence: float | None = None
