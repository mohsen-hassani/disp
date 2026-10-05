"""LLMCall — the call-site contract passed to LLMFacade.generate() and
friends (M19-llm.md §2, §4)."""

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

# Same two-segment "<domain>.<name>" shape as disp.core.contract.KEY_RE (tile
# keys, job names, notification types) — a call name is the grouping key for
# usage accounting (§6) and the lookup key for FakeLLM responses (§9), the
# same role those other registries play.
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}\.[a-z][a-z0-9_]{1,63}$")

Effort = Literal["low", "medium", "high", "xhigh", "max"]

# Half of the smallest current model's 200K-token context window, leaving
# headroom for the system prompt, up to `llm_max_output_tokens` (16K by
# default), and one repair-turn's overhead without approaching the hard
# ceiling. Not derived from the spec text — a deliberately conservative
# default a caller may tighten via LLMCall.max_input_tokens.
DEFAULT_MAX_INPUT_TOKENS = 100_000


@dataclass(frozen=True)
class LLMCall:
    name: str
    schema: type[BaseModel] | None
    system: str
    max_output_tokens: int
    effort: Effort = "high"
    max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS

    def __post_init__(self) -> None:
        if not KEY_RE.match(self.name):
            raise ValueError(f"LLMCall.name {self.name!r} must match {KEY_RE.pattern}")
