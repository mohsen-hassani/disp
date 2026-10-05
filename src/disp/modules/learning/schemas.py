from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CourseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None)


class CourseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None)


class CourseOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class SourceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    course_id: UUID
    title: str
    content_type: str
    token_count: int
    created_at: datetime


class JobOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    course_id: UUID
    kind: str
    status: str
    phase: str | None
    progress_current: int
    progress_total: int
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class PathItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1)
    tier: str | None = Field(default=None)
    order_index: int | None = Field(default=None, ge=0)
    # Reassigns which topics this lesson covers — the mechanism available
    # for "merge"/"split" edits (§18.2 declares no dedicated route for
    # either; see path.py's module docstring).
    topic_ids: list[UUID] | None = Field(default=None)


class PathItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    course_id: UUID
    tier: str
    order_index: int
    title: str
    est_minutes: int
    status: str
    completion_status: str
    completed_at: datetime | None
    topic_ids: list[UUID]


class SourceSectionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    heading_path: str
    content_text: str


class PathItemContentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path_item: PathItemOut
    sections: list[SourceSectionOut]


# --- §10/§11: quiz and exercise sessions -----------------------------------
#
# Quiz and exercise share one state-machine engine (`service/sessions.py`)
# but have genuinely different wire shapes (question_text vs
# instruction_text/hint_text, score vs passed), so their schemas are not
# shared — `internal_rubric` in particular must never appear on any
# Exercise*Out model (§3.4).


class QuizItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_text: str | None = Field(default=None, min_length=1)
    order_index: int | None = Field(default=None, ge=0)
    target_tag_ids: list[UUID] | None = Field(default=None)


class QuizItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    order_index: int
    question_text: str
    target_tag_ids: list[UUID]
    status: str


class QuizAnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_text: str = Field(min_length=1)


class QuizAnswerOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    question_id: UUID
    answer_text: str
    score: float
    feedback_text: str
    tags_tested: list[UUID]
    created_at: datetime


class FollowupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)


class FollowupOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    role: str
    content: str
    created_at: datetime


class QuizSessionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    path_item_id: UUID
    status: str
    current_question_index: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    questions: list[QuizItemOut]


class QuizSummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_score: float
    question_count: int
    answers: list[QuizAnswerOut]
    weakest_tag_ids: list[UUID]


class ExerciseItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction_text: str | None = Field(default=None, min_length=1)
    hint_text: str | None = Field(default=None)
    order_index: int | None = Field(default=None, ge=0)
    target_tag_ids: list[UUID] | None = Field(default=None)


class ExerciseItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    order_index: int
    instruction_text: str
    hint_text: str | None
    target_tag_ids: list[UUID]
    status: str
    # Deliberately no `internal_rubric` field (§3.4) — it never crosses the
    # API boundary, so there is nowhere on this model to put it.


class ExerciseSubmissionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_text: str = Field(min_length=1)


class ExerciseSubmissionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    step_id: UUID
    submission_text: str
    passed: bool
    feedback_text: str
    created_at: datetime


class ExerciseSessionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    path_item_id: UUID
    status: str
    current_step_index: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    steps: list[ExerciseItemOut]


class ExerciseSummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pass_rate: float
    step_count: int
    submissions: list[ExerciseSubmissionOut]
    weakest_tag_ids: list[UUID]


# --- §12: explain --------------------------------------------------------


class ExplainIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = Field(pattern="^(explain|guide|summarize)$")


class ExplainOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str


# --- §13: scoped chat ------------------------------------------------------


class ChatSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_type: str = Field(pattern="^(path_item|custom|freeform)$")
    title: str | None = Field(default=None)
    # Required (and meaningful) only for scope_type="path_item".
    path_item_id: UUID | None = Field(default=None)
    # Required (and meaningful) only for scope_type="custom".
    path_item_ids: list[UUID] | None = Field(default=None)


class ChatSessionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    course_id: UUID
    scope_type: str
    title: str | None
    created_at: datetime


class ChatMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    role: str
    content: str
    created_at: datetime


# --- §14: notes --------------------------------------------------------


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(default="note", pattern="^(note|todo|question|extra)$")
    body: str = Field(min_length=1, max_length=10000)
    path_item_id: UUID | None = Field(default=None)
    topic_id: UUID | None = Field(default=None)
    source_section_id: UUID | None = Field(default=None)


class NoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, pattern="^(note|todo|question|extra)$")
    body: str | None = Field(default=None, min_length=1, max_length=10000)


class NoteOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    course_id: UUID
    label: str
    body: str
    path_item_id: UUID | None
    topic_id: UUID | None
    source_section_id: UUID | None
    created_at: datetime
    updated_at: datetime


# --- §15: mastery, progress, weak points -----------------------------------


class TierProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    completed: int


class ProgressOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completed: int
    total: int
    by_tier: dict[str, TierProgress]


class WeakPointPathItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str


class WeakPointOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_tag_id: UUID
    tag_name: str
    topic_id: UUID
    topic_name: str
    rolling_score: float
    path_items: list[WeakPointPathItem]
