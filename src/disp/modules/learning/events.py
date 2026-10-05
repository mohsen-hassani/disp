"""§22. Published with `publish_after_commit(session, event)`, subscribed in
`register(platform)`.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CourseIndexed:
    course_id: UUID
    user_id: UUID
    topic_count: int
    unmatched_count: int


@dataclass(frozen=True, slots=True)
class PathItemCompleted:
    course_id: UUID
    path_item_id: UUID
    user_id: UUID
    score: float


@dataclass(frozen=True, slots=True)
class MasteryUpdated:
    course_id: UUID
    user_id: UUID
    topic_tag_id: UUID
    old_score: float
    new_score: float
