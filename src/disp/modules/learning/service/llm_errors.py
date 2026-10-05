"""Shared LLM-error -> AppError translation for every *synchronous* (HTTP
request-path) call site — quiz/exercise create and submit, chat, explain.

Background-job call sites (`service/ingest.py`'s `run_index_job`,
`service/path.py`'s `run_generate_path_job`) do NOT use this: a job has no
HTTP response to translate an error into, so it writes `job.error_code`
instead (see each file's own `_map_*_error_code`).

§24: `modules.learning.llm_unavailable`/`llm_refused` are the deliberate
exception to "a module must not re-code a core error" — they translate an
*internal service* failure into a *domain* outcome the caller can act on,
and neither has a `core.*` equivalent a client could key on instead.
"""

from disp.core.errors import AppError
from disp.core.llm import LLMNotConfigured, LLMRefused, LLMUnavailable

#: Every LLM exception type a synchronous call site should catch and
#: translate via `translate_llm_error` before it reaches a client as a
#: bare 500.
LLM_ERROR_TYPES = (LLMNotConfigured, LLMRefused, LLMUnavailable)


def translate_llm_error(exc: Exception) -> AppError:
    if isinstance(exc, LLMRefused):
        return AppError(
            status_code=422,
            code="modules.learning.llm_refused",
            title="The model declined to respond",
            detail=str(exc),
        )
    return AppError(
        status_code=503,
        code="modules.learning.llm_unavailable",
        title="AI features are temporarily unavailable",
        detail=str(exc),
    )
