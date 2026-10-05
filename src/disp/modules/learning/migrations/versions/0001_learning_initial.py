"""learning schema initial

Revision ID: 0001_learning_initial
Revises:
Create Date: 2026-08-10

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_learning_initial"
down_revision: str | None = None
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS learning")
    # Requires the pgvector/pgvector:pg16 image (M19 §7). Lives in this
    # module's own migration, not a core one: core has no vector column, and
    # a deployment running only notes/plants should not carry the extension.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- §5.1 Course, sources, sections ---------------------------------

    op.execute("""
        CREATE TABLE learning.course (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID        NOT NULL,
            title       TEXT        NOT NULL,
            description TEXT,
            status      TEXT        NOT NULL DEFAULT 'draft',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at  TIMESTAMPTZ,
            CONSTRAINT ck_course_status CHECK (status IN ('draft','indexing','active','archived')),
            CONSTRAINT ck_course_title_len CHECK (char_length(title) BETWEEN 1 AND 200)
        )
    """)
    op.execute("""
        CREATE INDEX ix_learning_course_user_created
            ON learning.course (user_id, created_at DESC) WHERE deleted_at IS NULL
    """)

    op.execute("""
        CREATE TABLE learning.source (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            course_id    UUID        NOT NULL REFERENCES learning.course(id) ON DELETE CASCADE,
            title        TEXT        NOT NULL,
            content_type TEXT        NOT NULL,
            asset_id     UUID,
            raw_text     TEXT        NOT NULL,
            token_count  INTEGER     NOT NULL DEFAULT 0,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_source_content_type
                CHECK (content_type IN ('markdown','html','srt','plain_text','pdf'))
        )
    """)
    op.execute("CREATE INDEX ix_learning_source_course ON learning.source (course_id, created_at)")

    op.execute("""
        CREATE TABLE learning.source_section (
            id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            source_id     UUID        NOT NULL REFERENCES learning.source(id) ON DELETE CASCADE,
            heading_path  TEXT        NOT NULL,
            order_index   INTEGER     NOT NULL,
            start_ref     TEXT,
            end_ref       TEXT,
            content_text  TEXT        NOT NULL,
            token_count   INTEGER     NOT NULL DEFAULT 0,
            embedding     vector(1024),
            search_tsv    TSVECTOR GENERATED ALWAYS AS
                              (to_tsvector('simple', coalesce(heading_path,'') || ' ' || content_text))
                              STORED,
            CONSTRAINT uq_section_source_order UNIQUE (source_id, order_index)
        )
    """)
    op.execute("""
        CREATE INDEX ix_learning_section_source
            ON learning.source_section (source_id, order_index)
    """)
    op.execute("""
        CREATE INDEX ix_learning_section_tsv
            ON learning.source_section USING gin (search_tsv)
    """)
    op.execute("""
        CREATE INDEX ix_learning_section_embedding ON learning.source_section
            USING hnsw (embedding vector_cosine_ops)
    """)

    # --- §5.2 Topics and tags --------------------------------------------

    op.execute("""
        CREATE TABLE learning.topic (
            id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            course_id          UUID        NOT NULL REFERENCES learning.course(id) ON DELETE CASCADE,
            canonical_name     TEXT        NOT NULL,
            description        TEXT,
            aggregated_summary TEXT,
            embedding          vector(1024),
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_topic_course_name UNIQUE (course_id, canonical_name)
        )
    """)

    op.execute("""
        CREATE TABLE learning.topic_source_section (
            topic_id          UUID NOT NULL REFERENCES learning.topic(id) ON DELETE CASCADE,
            source_section_id UUID NOT NULL REFERENCES learning.source_section(id) ON DELETE CASCADE,
            PRIMARY KEY (topic_id, source_section_id)
        )
    """)
    op.execute("""
        CREATE INDEX ix_learning_tss_section
            ON learning.topic_source_section (source_section_id)
    """)

    op.execute("""
        CREATE TABLE learning.topic_tag (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            topic_id   UUID        NOT NULL REFERENCES learning.topic(id) ON DELETE CASCADE,
            name       TEXT        NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_tag_topic_name UNIQUE (topic_id, name)
        )
    """)

    # --- §5.3 Path ---------------------------------------------------------

    op.execute("""
        CREATE TABLE learning.path_item (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            course_id         UUID        NOT NULL REFERENCES learning.course(id) ON DELETE CASCADE,
            tier              TEXT        NOT NULL,
            order_index       INTEGER     NOT NULL,
            title             TEXT        NOT NULL,
            est_minutes       INTEGER     NOT NULL DEFAULT 30,
            status            TEXT        NOT NULL DEFAULT 'draft',
            completion_status TEXT        NOT NULL DEFAULT 'not_started',
            completed_at      TIMESTAMPTZ,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_path_item_tier
                CHECK (tier IN ('concepts','beginner','intermediate','advanced')),
            CONSTRAINT ck_path_item_status CHECK (status IN ('draft','approved')),
            CONSTRAINT ck_path_item_completion
                CHECK (completion_status IN ('not_started','in_progress','completed')),
            CONSTRAINT ck_path_item_completed_at
                CHECK ((completion_status = 'completed') = (completed_at IS NOT NULL))
        )
    """)
    op.execute("""
        CREATE INDEX ix_learning_path_item_course ON learning.path_item (course_id, order_index)
    """)

    op.execute("""
        CREATE TABLE learning.path_item_topic (
            path_item_id UUID NOT NULL REFERENCES learning.path_item(id) ON DELETE CASCADE,
            topic_id     UUID NOT NULL REFERENCES learning.topic(id) ON DELETE CASCADE,
            PRIMARY KEY (path_item_id, topic_id)
        )
    """)

    # --- §5.4 Quiz -----------------------------------------------------

    op.execute("""
        CREATE TABLE learning.quiz_session (
            id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            path_item_id           UUID        NOT NULL REFERENCES learning.path_item(id) ON DELETE CASCADE,
            user_id                UUID        NOT NULL,
            status                 TEXT        NOT NULL DEFAULT 'draft',
            current_question_index INTEGER     NOT NULL DEFAULT 0,
            created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at             TIMESTAMPTZ,
            completed_at           TIMESTAMPTZ,
            CONSTRAINT ck_quiz_session_status CHECK (status IN ('draft','in_progress','completed'))
        )
    """)
    op.execute("""
        CREATE INDEX ix_learning_quiz_session_item
            ON learning.quiz_session (path_item_id, created_at DESC)
    """)

    op.execute("""
        CREATE TABLE learning.quiz_question (
            id              UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
            quiz_session_id UUID    NOT NULL REFERENCES learning.quiz_session(id) ON DELETE CASCADE,
            order_index     INTEGER NOT NULL,
            question_text   TEXT    NOT NULL,
            target_tag_ids  UUID[]  NOT NULL DEFAULT '{}',
            status          TEXT    NOT NULL DEFAULT 'pending',
            CONSTRAINT ck_quiz_question_status CHECK (status IN ('pending','answered')),
            CONSTRAINT uq_quiz_question_order UNIQUE (quiz_session_id, order_index)
        )
    """)

    op.execute("""
        CREATE TABLE learning.quiz_answer (
            id            UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
            question_id   UUID             NOT NULL UNIQUE
                                           REFERENCES learning.quiz_question(id) ON DELETE CASCADE,
            answer_text   TEXT             NOT NULL,
            score         DOUBLE PRECISION NOT NULL,
            feedback_text TEXT             NOT NULL,
            tags_tested   UUID[]           NOT NULL DEFAULT '{}',
            created_at    TIMESTAMPTZ      NOT NULL DEFAULT now(),
            CONSTRAINT ck_quiz_answer_score CHECK (score >= 0.0 AND score <= 1.0)
        )
    """)

    op.execute("""
        CREATE TABLE learning.quiz_followup (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            question_id UUID        NOT NULL REFERENCES learning.quiz_question(id) ON DELETE CASCADE,
            role        TEXT        NOT NULL,
            content     TEXT        NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_quiz_followup_role CHECK (role IN ('user','assistant'))
        )
    """)
    op.execute("""
        CREATE INDEX ix_learning_quiz_followup_q ON learning.quiz_followup (question_id, created_at)
    """)

    # --- §5.5 Exercises --------------------------------------------------

    op.execute("""
        CREATE TABLE learning.exercise_session (
            id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            path_item_id           UUID        NOT NULL REFERENCES learning.path_item(id) ON DELETE CASCADE,
            user_id                UUID        NOT NULL,
            status                 TEXT        NOT NULL DEFAULT 'draft',
            current_step_index     INTEGER     NOT NULL DEFAULT 0,
            created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at             TIMESTAMPTZ,
            completed_at           TIMESTAMPTZ,
            CONSTRAINT ck_exercise_session_status
                CHECK (status IN ('draft','in_progress','completed'))
        )
    """)
    op.execute("""
        CREATE INDEX ix_learning_exercise_session_item
            ON learning.exercise_session (path_item_id, created_at DESC)
    """)

    op.execute("""
        CREATE TABLE learning.exercise_step (
            id                  UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
            exercise_session_id UUID    NOT NULL
                                        REFERENCES learning.exercise_session(id) ON DELETE CASCADE,
            order_index         INTEGER NOT NULL,
            instruction_text    TEXT    NOT NULL,
            hint_text           TEXT,
            internal_rubric     TEXT    NOT NULL,
            target_tag_ids      UUID[]  NOT NULL DEFAULT '{}',
            status              TEXT    NOT NULL DEFAULT 'pending',
            CONSTRAINT ck_exercise_step_status CHECK (status IN ('pending','submitted')),
            CONSTRAINT uq_exercise_step_order UNIQUE (exercise_session_id, order_index)
        )
    """)

    op.execute("""
        CREATE TABLE learning.exercise_submission (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            step_id         UUID        NOT NULL UNIQUE
                                        REFERENCES learning.exercise_step(id) ON DELETE CASCADE,
            submission_text TEXT        NOT NULL,
            passed          BOOLEAN     NOT NULL,
            feedback_text   TEXT        NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE learning.exercise_followup (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            step_id    UUID        NOT NULL REFERENCES learning.exercise_step(id) ON DELETE CASCADE,
            role       TEXT        NOT NULL,
            content    TEXT        NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_exercise_followup_role CHECK (role IN ('user','assistant'))
        )
    """)
    op.execute("""
        CREATE INDEX ix_learning_exercise_followup_step
            ON learning.exercise_followup (step_id, created_at)
    """)

    # --- §5.6 Chat, notes, mastery, jobs ----------------------------------

    op.execute("""
        CREATE TABLE learning.chat_session (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            course_id  UUID        NOT NULL REFERENCES learning.course(id) ON DELETE CASCADE,
            user_id    UUID        NOT NULL,
            scope_type TEXT        NOT NULL,
            title      TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_chat_scope_type CHECK (scope_type IN ('path_item','custom','freeform'))
        )
    """)

    op.execute("""
        CREATE TABLE learning.chat_session_scope (
            chat_session_id UUID NOT NULL REFERENCES learning.chat_session(id) ON DELETE CASCADE,
            path_item_id    UUID NOT NULL REFERENCES learning.path_item(id) ON DELETE CASCADE,
            PRIMARY KEY (chat_session_id, path_item_id)
        )
    """)

    op.execute("""
        CREATE TABLE learning.chat_message (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            chat_session_id UUID        NOT NULL REFERENCES learning.chat_session(id) ON DELETE CASCADE,
            role            TEXT        NOT NULL,
            content         TEXT        NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_chat_message_role CHECK (role IN ('user','assistant'))
        )
    """)
    op.execute("""
        CREATE INDEX ix_learning_chat_message_session
            ON learning.chat_message (chat_session_id, created_at DESC, id DESC)
    """)

    op.execute("""
        CREATE TABLE learning.note (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            course_id         UUID        NOT NULL REFERENCES learning.course(id) ON DELETE CASCADE,
            user_id           UUID        NOT NULL,
            label             TEXT        NOT NULL DEFAULT 'note',
            body              TEXT        NOT NULL,
            path_item_id      UUID        REFERENCES learning.path_item(id) ON DELETE SET NULL,
            topic_id          UUID        REFERENCES learning.topic(id) ON DELETE SET NULL,
            source_section_id UUID        REFERENCES learning.source_section(id) ON DELETE SET NULL,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at        TIMESTAMPTZ,
            CONSTRAINT ck_note_label CHECK (label IN ('note','todo','question','extra')),
            CONSTRAINT ck_note_body_len CHECK (char_length(body) BETWEEN 1 AND 10000),
            CONSTRAINT ck_note_single_anchor CHECK (
                (path_item_id IS NOT NULL)::int
              + (topic_id IS NOT NULL)::int
              + (source_section_id IS NOT NULL)::int <= 1
            )
        )
    """)
    op.execute("""
        CREATE INDEX ix_learning_note_course_created
            ON learning.note (course_id, created_at DESC) WHERE deleted_at IS NULL
    """)
    op.execute("""
        CREATE INDEX ix_learning_note_path_item
            ON learning.note (path_item_id) WHERE path_item_id IS NOT NULL AND deleted_at IS NULL
    """)

    op.execute("""
        CREATE TABLE learning.topic_tag_score (
            id               UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
            topic_tag_id     UUID             NOT NULL REFERENCES learning.topic_tag(id) ON DELETE CASCADE,
            user_id          UUID             NOT NULL,
            rolling_score    DOUBLE PRECISION NOT NULL,
            attempts_count   INTEGER          NOT NULL DEFAULT 0,
            last_practiced_at TIMESTAMPTZ,
            CONSTRAINT uq_tag_score_tag_user UNIQUE (topic_tag_id, user_id),
            CONSTRAINT ck_tag_score_range CHECK (rolling_score >= 0.0 AND rolling_score <= 1.0)
        )
    """)

    op.execute("""
        CREATE TABLE learning.job (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            course_id        UUID        NOT NULL REFERENCES learning.course(id) ON DELETE CASCADE,
            user_id          UUID        NOT NULL,
            kind             TEXT        NOT NULL,
            status           TEXT        NOT NULL DEFAULT 'queued',
            phase            TEXT,
            progress_current INTEGER     NOT NULL DEFAULT 0,
            progress_total   INTEGER     NOT NULL DEFAULT 0,
            error_code       TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at       TIMESTAMPTZ,
            finished_at      TIMESTAMPTZ,
            CONSTRAINT ck_job_kind CHECK (kind IN ('index_course','generate_path')),
            CONSTRAINT ck_job_status CHECK (status IN ('queued','running','succeeded','failed'))
        )
    """)
    op.execute("CREATE INDEX ix_learning_job_course ON learning.job (course_id, created_at DESC)")
    op.execute("""
        CREATE UNIQUE INDEX uq_learning_job_active ON learning.job (course_id, kind)
            WHERE status IN ('queued','running')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS learning.job")
    op.execute("DROP TABLE IF EXISTS learning.topic_tag_score")
    op.execute("DROP TABLE IF EXISTS learning.note")
    op.execute("DROP TABLE IF EXISTS learning.chat_message")
    op.execute("DROP TABLE IF EXISTS learning.chat_session_scope")
    op.execute("DROP TABLE IF EXISTS learning.chat_session")
    op.execute("DROP TABLE IF EXISTS learning.exercise_followup")
    op.execute("DROP TABLE IF EXISTS learning.exercise_submission")
    op.execute("DROP TABLE IF EXISTS learning.exercise_step")
    op.execute("DROP TABLE IF EXISTS learning.exercise_session")
    op.execute("DROP TABLE IF EXISTS learning.quiz_followup")
    op.execute("DROP TABLE IF EXISTS learning.quiz_answer")
    op.execute("DROP TABLE IF EXISTS learning.quiz_question")
    op.execute("DROP TABLE IF EXISTS learning.quiz_session")
    op.execute("DROP TABLE IF EXISTS learning.path_item_topic")
    op.execute("DROP TABLE IF EXISTS learning.path_item")
    op.execute("DROP TABLE IF EXISTS learning.topic_tag")
    op.execute("DROP TABLE IF EXISTS learning.topic_source_section")
    op.execute("DROP TABLE IF EXISTS learning.topic")
    op.execute("DROP TABLE IF EXISTS learning.source_section")
    op.execute("DROP TABLE IF EXISTS learning.source")
    op.execute("DROP TABLE IF EXISTS learning.course")
