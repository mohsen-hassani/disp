from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class NoteCreated:
    note_id: UUID
    user_id: UUID
    title: str | None


@dataclass(frozen=True, slots=True)
class NoteUpdated:
    note_id: UUID
    user_id: UUID


@dataclass(frozen=True, slots=True)
class NoteDeleted:
    note_id: UUID
    user_id: UUID
