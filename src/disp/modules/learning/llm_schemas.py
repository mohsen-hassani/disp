"""§17: output schemas for every `platform.llm.generate()` call this module
makes. Free-text calls (`learning.chat`, `learning.explain`,
`learning.followup`) use `generate_text()` and have no schema here.

Every schema that carries an id list carries ids the caller supplied in the
same prompt (never a name) — §3.3's "tags are closed-world" invariant is
enforced by the service layer discarding any id that doesn't resolve, not by
asking the model nicely. Grown incrementally, one call site's worth of
schemas per phase, the way `courses.py`'s spec-section discipline expects.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    start_ts: str
    end_ts: str


class TranscriptSegments(BaseModel):
    """§8.2: one `learning.segment_transcript` call per map-reduce chunk."""

    model_config = ConfigDict(extra="forbid")

    segments: list[TranscriptSegment]


class AlignedTopic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    member_section_ids: list[UUID]


class TopicAlignment(BaseModel):
    """§8.3: the one `learning.align_topics` call per course."""

    model_config = ConfigDict(extra="forbid")

    topics: list[AlignedTopic]
    unmatched_section_ids: list[UUID]


class TopicTags(BaseModel):
    """§8.4: one `learning.generate_tags` call per (newly created) topic."""

    model_config = ConfigDict(extra="forbid")

    names: list[str] = Field(min_length=3, max_length=6)


class TopicSummary(BaseModel):
    """§8.4: one `learning.summarize_topic` call per (newly created) topic."""

    model_config = ConfigDict(extra="forbid")

    summary: str


class PathItemDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    tier: str
    topic_ids: list[UUID]
    est_minutes: int


class LearningPathDraft(BaseModel):
    """§9: the one `learning.generate_path` call per course. Wrapped in an
    `items` object (rather than a bare list) because every LLM output schema
    here is a Pydantic model, and Pydantic has no top-level-list model."""

    model_config = ConfigDict(extra="forbid")

    items: list[PathItemDraft]


class QuizQuestionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_text: str
    target_tag_ids: list[UUID]


class QuizDraft(BaseModel):
    """§10: one `learning.generate_quiz` call per quiz session create."""

    model_config = ConfigDict(extra="forbid")

    questions: list[QuizQuestionDraft]


class QuizGrade(BaseModel):
    """§10: one `learning.grade_quiz` call per submitted answer."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=1.0)
    feedback_text: str
    tags_tested: list[UUID]


class ExerciseStepDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction_text: str
    hint_text: str | None = None
    internal_rubric: str
    target_tag_ids: list[UUID]


class ExerciseDraft(BaseModel):
    """§11: one `learning.generate_exercise` call per exercise session create."""

    model_config = ConfigDict(extra="forbid")

    steps: list[ExerciseStepDraft]


class ExerciseGrade(BaseModel):
    """§11: one `learning.grade_exercise` call per submission."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    feedback_text: str
    tags_tested: list[UUID]
