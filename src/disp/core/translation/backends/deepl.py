"""DeepL backend — the only file in src/ that names the vendor's host (T1).

No `deepl` SDK on purpose (M22-translation.md §4.1): the official package is a
second HTTP stack whose principal value is exactly the sync/async split
HTTPTranslationBackend already provides, and adding it would put a vendor name
in the dependency graph for no gain.
"""

from typing import Any

from disp.core.translation.backends.base import HTTPCall, HTTPTranslationBackend
from disp.core.translation.errors import TranslationInvalidResponse
from disp.core.translation.schema import (
    Detected,
    DetectRequest,
    Feature,
    Translated,
    TranslateRequest,
)

# A free-tier key ends in ":fx" and MUST be sent to the free host; a pro key
# MUST go to the paid one. Crossing them returns a 403 whose message reads
# like a bad credential, which is the most misleading failure available.
FREE_KEY_SUFFIX = ":fx"
FREE_BASE_URL = "https://api-free.deepl.com"
PRO_BASE_URL = "https://api.deepl.com"

# DeepL has no standalone detect endpoint: detection is a translate call with
# the source omitted, reading back `detected_source_language`. The target has
# to be *something*; this one is arbitrary and never surfaces to the caller.
DETECT_TARGET_LANG = "EN-US"


def base_url_for(api_key: str, configured: str) -> str:
    """An explicit DISP_TRANSLATION_BASE_URL always wins — a self-hosted proxy
    is a legitimate reason to override. Otherwise the host is derived from the
    key's suffix."""
    if configured:
        return configured.rstrip("/")
    return FREE_BASE_URL if api_key.endswith(FREE_KEY_SUFFIX) else PRO_BASE_URL


class DeepLBackend(HTTPTranslationBackend):
    name = "deepl"
    supports = frozenset({Feature.TRANSLATE, Feature.DETECT, Feature.FORMALITY})

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "",
        timeout_seconds: int,
        max_retries: int,
        **transports: Any,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, max_retries=max_retries, **transports)
        self._api_key = api_key
        self._base_url = base_url_for(api_key, base_url)

    @property
    def base_url(self) -> str:
        return self._base_url

    def _headers(self) -> dict[str, str]:
        # DeepL-Auth-Key, not Bearer.
        return {"Authorization": f"DeepL-Auth-Key {self._api_key}"}

    def _build_translate(self, req: TranslateRequest) -> HTTPCall:
        body: dict[str, Any] = {"text": list(req.texts), "target_lang": req.target_lang}
        if req.source_lang:
            body["source_lang"] = req.source_lang
        if req.formality:
            body["formality"] = req.formality
        return HTTPCall(
            method="POST",
            url=f"{self._base_url}/v2/translate",
            headers=self._headers(),
            json=body,
        )

    def _build_detect(self, req: DetectRequest) -> HTTPCall:
        # Omitting source_lang is what makes this a detection; see the
        # DETECT_TARGET_LANG comment above. This costs characters like any
        # other translate call, which is why the facade records them (§4.1).
        return HTTPCall(
            method="POST",
            url=f"{self._base_url}/v2/translate",
            headers=self._headers(),
            json={"text": list(req.texts), "target_lang": DETECT_TARGET_LANG},
        )

    def _read_translate(self, payload: Any) -> list[Translated]:
        return [
            Translated(
                text=item["text"],
                detected_source_lang=item.get("detected_source_language"),
            )
            for item in _translations(payload)
        ]

    def _read_detect(self, payload: Any) -> list[Detected]:
        return [
            Detected(lang=item.get("detected_source_language") or "")
            for item in _translations(payload)
        ]


def _translations(payload: Any) -> list[dict[str, Any]]:
    try:
        translations = payload["translations"]
    except (KeyError, TypeError) as exc:
        raise TranslationInvalidResponse("deepl response has no 'translations' array") from exc
    if not isinstance(translations, list):
        raise TranslationInvalidResponse("deepl 'translations' is not an array")
    return translations
