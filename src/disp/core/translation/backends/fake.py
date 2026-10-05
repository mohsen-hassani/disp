"""FakeTranslationBackend — the test double (M22-translation.md §4.2).

Part of the public surface, because module tests need it, and selected in a
real deployment by DISP_TRANSLATION_BACKEND=fake.

It is a fake *backend*, not a fake facade — a deliberate departure from M19
§9's FakeLLM, which duck-types the whole facade. Replacing the facade means a
test never exercises the usage row, the character budget, the feature gate,
the error mapping or the sync/async wiring; every one of those is production
code that only runs when something is stubbed *below* it. Putting the seam at
the network boundary means the facade under test is the real one.
"""

import hashlib
from dataclasses import dataclass

from disp.core.translation.errors import TranslationError, TranslationNotSupported
from disp.core.translation.schema import (
    Detected,
    DetectRequest,
    Feature,
    Formality,
    Translated,
    TranslateRequest,
)

DEFAULT_SUPPORTS = frozenset({Feature.TRANSLATE, Feature.DETECT, Feature.FORMALITY})

# Small closed set so a hash-derived detection is reproducible across runs.
_DETECTABLE_LANGS = ("EN", "DE", "FR", "ES", "NL", "IT")


@dataclass(frozen=True)
class RecordedCall:
    operation: str
    texts: tuple[str, ...]
    target_lang: str | None = None
    source_lang: str | None = None
    formality: Formality | None = None


def deterministic_lang(text: str) -> str:
    """Hash-derived, reproducible language code — so detection assertions do
    not depend on run order, the way llm.embeddings.deterministic_vector keeps
    similarity assertions reproducible."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return _DETECTABLE_LANGS[digest[0] % len(_DETECTABLE_LANGS)]


class FakeTranslationBackend:
    name = "fake"

    def __init__(self, *, supports: frozenset[Feature] = DEFAULT_SUPPORTS) -> None:
        # `supports` is a constructor argument here and a class constant
        # everywhere else: it is the only way to exercise T4 without shipping
        # a second real provider.
        self.supports = supports
        self._results: dict[tuple[str, str], str] = {}
        self._detections: dict[str, str] = {}
        self._errors: dict[str, TranslationError] = {}
        self.calls: list[RecordedCall] = []

    # ---- registration ----

    def register(self, text: str, *, target_lang: str, result: str) -> None:
        self._results[(text, target_lang)] = result

    def register_detection(self, text: str, *, lang: str) -> None:
        self._detections[text] = lang

    def register_error(self, text: str, *, error: TranslationError) -> None:
        """Keyed on the source text, so one batch can mix registered results
        and a registered failure."""
        self._errors[text] = error

    # ---- the four public methods ----

    async def translate(self, req: TranslateRequest) -> list[Translated]:
        return self._translate(req)

    def translate_sync(self, req: TranslateRequest) -> list[Translated]:
        return self._translate(req)

    async def detect(self, req: DetectRequest) -> list[Detected]:
        return self._detect(req)

    def detect_sync(self, req: DetectRequest) -> list[Detected]:
        return self._detect(req)

    async def aclose(self) -> None:
        return None

    def close(self) -> None:
        return None

    # ---- implementation ----

    def require(self, feature: Feature) -> None:
        if feature not in self.supports:
            raise TranslationNotSupported(backend=self.name, feature=feature)

    def _translate(self, req: TranslateRequest) -> list[Translated]:
        # Feature gate before recording, so `backend.calls == []` is the
        # fake's equivalent of "the transport saw no request" (T4).
        self.require(Feature.TRANSLATE)
        if req.formality is not None:
            self.require(Feature.FORMALITY)
        self.calls.append(
            RecordedCall(
                operation="translate",
                texts=req.texts,
                target_lang=req.target_lang,
                source_lang=req.source_lang,
                formality=req.formality,
            )
        )
        results: list[Translated] = []
        for text in req.texts:
            if text in self._errors:
                raise self._errors[text]
            # An unregistered text gets the identity transform rather than
            # raising: unlike FakeLLM, translation has a meaningful default,
            # and the marker proves the target language actually propagated
            # through the facade — which a raise would not (§4.2).
            translated = self._results.get((text, req.target_lang), f"[{req.target_lang}] {text}")
            results.append(
                Translated(
                    text=translated,
                    detected_source_lang=req.source_lang or deterministic_lang(text),
                )
            )
        return results

    def _detect(self, req: DetectRequest) -> list[Detected]:
        self.require(Feature.DETECT)
        self.calls.append(RecordedCall(operation="detect", texts=req.texts))
        results: list[Detected] = []
        for text in req.texts:
            if text in self._errors:
                raise self._errors[text]
            results.append(Detected(lang=self._detections.get(text, deterministic_lang(text))))
        return results
