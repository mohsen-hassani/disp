from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class LearningSettings(BaseSettings):
    """Module-owned configuration (§4).

    Deliberately a separate BaseSettings rather than fields on the core
    `Settings`: a module must not need a core change to be installable, and
    pydantic-settings ignores env vars that don't match this class's own
    `DISP_LEARNING_` prefix (core `Settings`' `extra="forbid"` does not trip
    on them — verified by `plants/config.py`).
    """

    model_config = SettingsConfigDict(env_prefix="DISP_LEARNING_", env_file=".env", extra="ignore")

    max_source_bytes: int = 10 * 1024 * 1024
    max_sources_per_course: int = 25
    quiz_questions_min: int = 5
    quiz_questions_max: int = 8
    exercise_steps_min: int = 3
    exercise_steps_max: int = 6
    target_item_minutes: int = 30
    # At 0.3, a single bad session moves a settled score by less than a
    # third — one distracted evening does not erase a month of evidence,
    # while five consecutive weak sessions move it decisively (§4, §15.1).
    mastery_alpha: float = 0.3
    alignment_similarity_threshold: float = 0.75
    chat_history_messages: int = 20
    # §13.3: how many sections the FTS+pgvector hybrid retrieves for a
    # freeform-scope chat message, after merge-dedup.
    chat_freeform_top_k: int = 8


@lru_cache
def get_learning_settings() -> LearningSettings:
    return LearningSettings()
