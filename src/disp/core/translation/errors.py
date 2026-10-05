"""TranslationError hierarchy — disp.core.translation's failure surface
(M22-translation.md §5.2, §9).

Plain Exception subclasses, deliberately NOT AppError subclasses, for the same
reason disp.core.llm's are: these are facade-level errors a *module* catches
and translates to its own AppError at its own route boundary. core.translation
has no HTTP endpoint of its own to translate at (§10's explicit non-goal), so
there is no response shape for these to carry here.

Each concrete error (other than TranslationNotConfigured) declares an
`outcome` class attribute matching one of core.translation_call's seven
CHECK-constrained values (§7). TranslationNotConfigured has no `outcome` and
writes no usage row at all — a config-gate rejection isn't a "call" in the
accounting sense, since no backend was ever constructed or dispatched to.

The error-code strings written into translation_call.error_code are
synthesised at the recording site as f"core.translation.{outcome}". They are
never emitted over HTTP, which is why they are absent from TECHNICAL-SPEC.md
Appendix A — see §9.
"""

from disp.core.translation.schema import Feature


class TranslationError(Exception):
    """Base class for every disp.core.translation error."""


class TranslationNotConfigured(TranslationError):
    """Raised when `translation_enabled` is false. Writes no
    core.translation_call row (see module docstring)."""


class TranslationNotSupported(TranslationError):
    """The backend does not implement the requested feature (T4).

    Raised by the backend itself, before any network request. Declaring the
    gap in `backend.supports` is not sufficient on its own: a caller that
    never consults `supports` must still get a typed refusal rather than a
    provider-shaped 400 or, worse, a plausible wrong answer.
    """

    outcome = "not_supported"

    def __init__(self, *, backend: str, feature: Feature) -> None:
        self.backend = backend
        self.feature = feature
        super().__init__(f"backend {backend!r} does not support {feature.value!r}")


class TranslationUnavailable(TranslationError):
    """Transport failure, timeout, 5xx or 429 — the upstream could not be
    reached or would not serve the request right now."""

    outcome = "unavailable"


class TranslationQuotaExceeded(TranslationError):
    """The provider's character budget is exhausted (DeepL 456).

    Its own type rather than a TranslationRejected because it is the one 4xx
    an *operator* must act on rather than a caller: reporting "bad request"
    when the month's budget ran out sends whoever is debugging it to read code
    instead of a billing page (§4.1).
    """

    outcome = "quota_exceeded"


class TranslationRejected(TranslationError):
    """A 4xx the caller caused: unknown language code, malformed request, bad
    credential."""

    outcome = "rejected"


class TranslationInputTooLarge(TranslationError):
    """The batch exceeds `translation_max_chars`, raised before any network
    request (T7). The facade never silently truncates or splits."""

    outcome = "too_large"

    def __init__(self, *, char_count: int, max_chars: int) -> None:
        self.char_count = char_count
        self.max_chars = max_chars
        super().__init__(
            f"batch is {char_count} characters, exceeding the {max_chars} character budget"
        )


class TranslationInvalidResponse(TranslationError):
    """The provider's payload could not be parsed, or came back with a
    different number of results than inputs (T8).

    The item-count case is the one that matters: a batch whose results are
    misaligned by one produces fluent output attached to the wrong record — a
    corruption with no visible symptom.
    """

    outcome = "invalid_response"
