"""LLMError hierarchy — disp.core.llm's failure surface (M19-llm.md §4.4, §10).

Plain Exception subclasses, deliberately NOT AppError subclasses: these are
facade-level errors a *module* catches and translates to its own AppError at
its own route boundary. core.llm itself has no generate()/embed() HTTP
endpoint to translate at (§11's explicit non-goal), so there is no response
shape for these to carry here.

Each concrete error (other than LLMNotConfigured) declares an `outcome`
class attribute matching one of core.llm_call's six CHECK-constrained
values (§6). LLMNotConfigured has no `outcome` and writes no usage row at
all — a config-gate rejection isn't a "call" in the accounting sense, since
no model was ever chosen or dispatched.
"""


class LLMError(Exception):
    """Base class for every disp.core.llm error."""


class LLMNotConfigured(LLMError):
    """Raised when `llm_enabled`/`embedding_enabled` is false. Writes no
    core.llm_call row (see module docstring)."""


class LLMUnavailable(LLMError):
    """Transport/5xx/429 with the SDK's own retries (`llm_max_retries`)
    exhausted."""

    outcome = "unavailable"


class LLMRefused(LLMError):
    """`stop_reason == "refusal"` (§4.4, L6)."""

    outcome = "refused"

    def __init__(self, *, category: str | None = None) -> None:
        self.category = category
        message = "The model declined to respond."
        if category:
            message = f"{message} (category: {category})"
        super().__init__(message)


class LLMTruncated(LLMError):
    """`stop_reason == "max_tokens"`. Not retried — a larger
    `max_output_tokens` is a code change, not a runtime decision."""

    outcome = "truncated"


class LLMInvalidOutput(LLMError):
    """Schema validation failed after the single repair attempt (§4.4)."""

    outcome = "invalid_output"


class LLMInputTooLarge(LLMError):
    """Input exceeds `LLMCall.max_input_tokens`, raised before any
    generation request (L5)."""

    outcome = "too_large"

    def __init__(self, *, input_tokens: int, max_input_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.max_input_tokens = max_input_tokens
        super().__init__(
            f"input is {input_tokens} tokens, exceeding the {max_input_tokens} token budget"
        )
