import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from disp.core.db import Base

SCHEMA = "learning"

# TECHNICAL-SPEC.md §5.1: the DDL and the config must agree — DISP_EMBEDDING_DIMENSIONS
# is pinned by M19 §7 for exactly this reason. Changing embedding models is a
# migration, not a config change.
EMBEDDING_DIMENSIONS = 1024

_UUID_ARRAY = ARRAY(PGUUID(as_uuid=True))


class Course(Base):
    """The aggregate root and the ACL boundary (§19) — one grant covers every
    child entity under it."""

    __tablename__ = "course"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','indexing','active','archived')", name="ck_course_status"
        ),
        CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="ck_course_title_len"),
        Index(
            "ix_learning_course_user_created",
            "user_id",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # No FK to core.users: modules must not create cross-schema foreign keys (§6.1).
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Source(Base):
    """One uploaded or pasted document. `raw_text` is stored even when
    `file_id` is set — the file is the original bytes for re-parsing and
    download, `raw_text` is what every query reads (§5.1)."""

    __tablename__ = "source"
    __table_args__ = (
        CheckConstraint(
            "content_type IN ('markdown','html','srt','plain_text','pdf')",
            name="ck_source_content_type",
        ),
        Index("ix_learning_source_course", "course_id", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.course.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    # A core.files id (M18-files.md) — bare column, no cross-schema FK, same
    # convention as user_id. NULL when the source was pasted rather than uploaded.
    file_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SourceSection(Base):
    """The atom of content: one leaf of a source's heading tree.

    `embedding` is NULL until §8.3's alignment fallback runs; `search_tsv` is
    a generated column so it never falls out of sync with `content_text`.
    """

    __tablename__ = "source_section"
    __table_args__ = (
        UniqueConstraint("source_id", "order_index", name="uq_section_source_order"),
        Index("ix_learning_section_source", "source_id", "order_index"),
        Index("ix_learning_section_tsv", "search_tsv", postgresql_using="gin"),
        Index(
            "ix_learning_section_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.source.id", ondelete="CASCADE"), nullable=False
    )
    heading_path: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # Char offset, or "00:14:02" for srt.
    start_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    end_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )
    search_tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(heading_path,'') || ' ' || content_text)",
            persisted=True,
        ),
    )


class Topic(Base):
    """The merged index: one concept, N sections across N sources (§3.1)."""

    __tablename__ = "topic"
    __table_args__ = (
        UniqueConstraint("course_id", "canonical_name", name="uq_topic_course_name"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.course.id", ondelete="CASCADE"), nullable=False
    )
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A few sentences; used by lighter calls (§9) so path generation reads
    # summaries rather than full section text.
    aggregated_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TopicSourceSection(Base):
    """M:N join: a topic covered by three books is one topic with three
    member sections, never a "canonical" source pick (§2)."""

    __tablename__ = "topic_source_section"
    __table_args__ = (
        Index("ix_learning_tss_section", "source_section_id"),
        {"schema": SCHEMA},
    )

    topic_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.topic.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_section_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.source_section.id", ondelete="CASCADE"),
        primary_key=True,
    )


class TopicTag(Base):
    """The unit mastery is measured in (§2). The closed world quiz/exercise
    generation must select from (§3.3)."""

    __tablename__ = "topic_tag"
    __table_args__ = (
        UniqueConstraint("topic_id", "name", name="uq_tag_topic_name"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.topic.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PathItem(Base):
    """One ~30-minute lesson, over one or more topics.

    `ck_path_item_completed_at` is a biconditional: `completed_at` is set
    exactly when the item is completed. A one-directional check would allow
    the state that breaks §15.2's progress query.
    """

    __tablename__ = "path_item"
    __table_args__ = (
        CheckConstraint(
            "tier IN ('concepts','beginner','intermediate','advanced')",
            name="ck_path_item_tier",
        ),
        CheckConstraint("status IN ('draft','approved')", name="ck_path_item_status"),
        CheckConstraint(
            "completion_status IN ('not_started','in_progress','completed')",
            name="ck_path_item_completion",
        ),
        CheckConstraint(
            "(completion_status = 'completed') = (completed_at IS NOT NULL)",
            name="ck_path_item_completed_at",
        ),
        Index("ix_learning_path_item_course", "course_id", "order_index"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.course.id", ondelete="CASCADE"), nullable=False
    )
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    est_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("30"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    completion_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'not_started'")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PathItemTopic(Base):
    """M:N join — a topic split across two path items, or several topics
    merged into one (§9)."""

    __tablename__ = "path_item_topic"
    __table_args__ = ({"schema": SCHEMA},)

    path_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.path_item.id", ondelete="CASCADE"),
        primary_key=True,
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.topic.id", ondelete="CASCADE"),
        primary_key=True,
    )


class QuizSession(Base):
    """`draft -> in_progress -> completed`, driven entirely by explicit
    actions (§3.2, §10)."""

    __tablename__ = "quiz_session"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','in_progress','completed')", name="ck_quiz_session_status"
        ),
        Index("ix_learning_quiz_session_item", "path_item_id", text("created_at DESC")),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    path_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.path_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    current_question_index: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QuizQuestion(Base):
    """`target_tag_ids` is a snapshot of intent at generation time — a join
    table would add two tables and buy nothing (§5.4)."""

    __tablename__ = "quiz_question"
    __table_args__ = (
        CheckConstraint("status IN ('pending','answered')", name="ck_quiz_question_status"),
        UniqueConstraint("quiz_session_id", "order_index", name="uq_quiz_question_order"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    quiz_session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.quiz_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_tag_ids: Mapped[list[uuid.UUID]] = mapped_column(
        _UUID_ARRAY, nullable=False, server_default=text("'{}'")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))


class QuizAnswer(Base):
    """`question_id` is UNIQUE so a double-submit race resolves as a
    constraint violation, not two `topic_tag_score` updates (§5.4)."""

    __tablename__ = "quiz_answer"
    __table_args__ = (
        CheckConstraint("score >= 0.0 AND score <= 1.0", name="ck_quiz_answer_score"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.quiz_question.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Double, nullable=False)
    feedback_text: Mapped[str] = mapped_column(Text, nullable=False)
    tags_tested: Mapped[list[uuid.UUID]] = mapped_column(
        _UUID_ARRAY, nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class QuizFollowup(Base):
    """Free-form Q&A on a just-graded question (§10)."""

    __tablename__ = "quiz_followup"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="ck_quiz_followup_role"),
        Index("ix_learning_quiz_followup_q", "question_id", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.quiz_question.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExerciseSession(Base):
    """As `QuizSession`, plus `current_step_index` (§5.5)."""

    __tablename__ = "exercise_session"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','in_progress','completed')", name="ck_exercise_session_status"
        ),
        Index("ix_learning_exercise_session_item", "path_item_id", text("created_at DESC")),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    path_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.path_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    current_step_index: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExerciseStep(Base):
    """`internal_rubric` is read server-side only, to grade a submission
    (§11.3) — it MUST NOT appear in any response model (§3.4)."""

    __tablename__ = "exercise_step"
    __table_args__ = (
        CheckConstraint("status IN ('pending','submitted')", name="ck_exercise_step_status"),
        UniqueConstraint("exercise_session_id", "order_index", name="uq_exercise_step_order"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    exercise_session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.exercise_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    instruction_text: Mapped[str] = mapped_column(Text, nullable=False)
    hint_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_rubric: Mapped[str] = mapped_column(Text, nullable=False)
    target_tag_ids: Mapped[list[uuid.UUID]] = mapped_column(
        _UUID_ARRAY, nullable=False, server_default=text("'{}'")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))


class ExerciseSubmission(Base):
    """A practical exercise either meets its rubric or it does not — `passed`
    is boolean, not a score (§5.5)."""

    __tablename__ = "exercise_submission"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    step_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.exercise_step.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    submission_text: Mapped[str] = mapped_column(Text, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    feedback_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExerciseFollowup(Base):
    """As `QuizFollowup`, keyed on `step_id` (§5.5)."""

    __tablename__ = "exercise_followup"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="ck_exercise_followup_role"),
        Index("ix_learning_exercise_followup_step", "step_id", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    step_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.exercise_step.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChatSession(Base):
    """The scope is fixed at creation; changing it means a new session (§13)."""

    __tablename__ = "chat_session"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('path_item','custom','freeform')", name="ck_chat_scope_type"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.course.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChatSessionScope(Base):
    """The union of several user-selected path items' sections, for
    `scope_type='custom'` (§13)."""

    __tablename__ = "chat_session_scope"
    __table_args__ = ({"schema": SCHEMA},)

    chat_session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.chat_session.id", ondelete="CASCADE"),
        primary_key=True,
    )
    path_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.path_item.id", ondelete="CASCADE"),
        primary_key=True,
    )


class ChatMessage(Base):
    __tablename__ = "chat_message"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="ck_chat_message_role"),
        Index(
            "ix_learning_chat_message_session",
            "chat_session_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    chat_session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.chat_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Note(Base):
    """At most one anchor — a path item, a topic, or a source section — or
    none, in which case the note belongs to the course generally (§14).

    Anchors are `ON DELETE SET NULL` while everything else cascades: a
    re-index (§8.5) must not delete a note the user wrote just because it
    reorganised the index underneath it.
    """

    __tablename__ = "note"
    __table_args__ = (
        CheckConstraint("label IN ('note','todo','question','extra')", name="ck_note_label"),
        CheckConstraint("char_length(body) BETWEEN 1 AND 10000", name="ck_note_body_len"),
        CheckConstraint(
            "(path_item_id IS NOT NULL)::int + (topic_id IS NOT NULL)::int "
            "+ (source_section_id IS NOT NULL)::int <= 1",
            name="ck_note_single_anchor",
        ),
        Index(
            "ix_learning_note_course_created",
            "course_id",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_learning_note_path_item",
            "path_item_id",
            postgresql_where=text("path_item_id IS NOT NULL AND deleted_at IS NULL"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.course.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'note'"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    path_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.path_item.id", ondelete="SET NULL"),
        nullable=True,
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.topic.id", ondelete="SET NULL"), nullable=True
    )
    source_section_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.source_section.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TopicTagScore(Base):
    """One EMA per (tag, user) — keyed on the pair rather than just the tag
    because a course can be shared (§19) and two people studying the same
    material must not share a mastery score."""

    __tablename__ = "topic_tag_score"
    __table_args__ = (
        UniqueConstraint("topic_tag_id", "user_id", name="uq_tag_score_tag_user"),
        CheckConstraint("rolling_score >= 0.0 AND rolling_score <= 1.0", name="ck_tag_score_range"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    topic_tag_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.topic_tag.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    rolling_score: Mapped[float] = mapped_column(Double, nullable=False)
    attempts_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_practiced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Job(Base):
    """Because indexing takes minutes and the user needs to see it happening
    (§16) — the first job-status surface in DISP.

    `uq_learning_job_active` is a partial unique index that makes "one active
    job per course per kind" a database guarantee: a double-clicked button
    produces `409 learning.job_already_running` rather than two workers
    writing the same topic set.
    """

    __tablename__ = "job"
    __table_args__ = (
        CheckConstraint("kind IN ('index_course','generate_path')", name="ck_job_kind"),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed')", name="ck_job_status"
        ),
        Index("ix_learning_job_course", "course_id", text("created_at DESC")),
        Index(
            "uq_learning_job_active",
            "course_id",
            "kind",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.course.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'queued'"))
    phase: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_current: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = [
    "ChatMessage",
    "ChatSession",
    "ChatSessionScope",
    "Course",
    "ExerciseFollowup",
    "ExerciseSession",
    "ExerciseStep",
    "ExerciseSubmission",
    "Job",
    "Note",
    "PathItem",
    "PathItemTopic",
    "QuizAnswer",
    "QuizFollowup",
    "QuizQuestion",
    "QuizSession",
    "Source",
    "SourceSection",
    "Topic",
    "TopicSourceSection",
    "TopicTag",
    "TopicTagScore",
]
