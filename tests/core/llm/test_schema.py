"""LLMCall.name validation against KEY_RE (M19-llm.md §2)."""

import pytest
from pydantic import BaseModel

from disp.core.llm import LLMCall


class _Schema(BaseModel):
    value: str


def test_llm_call_accepts_valid_name() -> None:
    call = LLMCall(name="learning.align_topics", schema=_Schema, system="s", max_output_tokens=100)
    assert call.name == "learning.align_topics"


@pytest.mark.parametrize(
    "name",
    ["NoDot", "has spaces.here", "Upper.case", "trailing.dot.", ".leading", "a.b!"],
)
def test_llm_call_rejects_invalid_name(name: str) -> None:
    with pytest.raises(ValueError, match="must match"):
        LLMCall(name=name, schema=_Schema, system="s", max_output_tokens=100)


def test_llm_call_default_max_input_tokens() -> None:
    call = LLMCall(name="learning.grade", schema=_Schema, system="s", max_output_tokens=100)
    assert call.max_input_tokens == 100_000
