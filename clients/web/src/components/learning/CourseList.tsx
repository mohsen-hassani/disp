import { useInfiniteQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import { AlertCircle, BookOpen, Plus } from 'lucide-react';
import { type FormEvent, type ReactElement, useState } from 'react';

import { learningCoursesInfiniteQueryOptions } from '../../api/queries';
import { EmptyState } from '../feedback/EmptyState';
import { SubmitButton } from '../feedback/SubmitButton';
import { useToast } from '../feedback/ToastProvider';
import { describeLearningError, useCreateCourse } from './useLearningMutations';

const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

const TITLE_MAX_LENGTH = 200;

const STATUS_LABEL: Record<string, string> = {
  draft: 'Draft',
  indexing: 'Indexing…',
  active: 'Active',
};

function CourseCreateForm({ onDone }: { onDone: () => void }): ReactElement {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const { showToast } = useToast();
  const createCourse = useCreateCourse();

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    createCourse.mutate(
      { title, description: description || undefined },
      {
        onSuccess: () => {
          showToast('Course created.', 'success');
          setTitle('');
          setDescription('');
          onDone();
        },
        onError: (error) => showToast(describeLearningError(error), 'error'),
      },
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="border-border bg-surface mb-4 flex flex-col gap-3 rounded-md border p-4"
    >
      <div className="flex flex-col gap-1">
        <label htmlFor="course-title" className="text-text text-sm font-medium">
          Title
        </label>
        <input
          id="course-title"
          type="text"
          required
          maxLength={TITLE_MAX_LENGTH}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          className="border-border bg-surface rounded-sm border px-3 py-2 text-sm"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="course-description" className="text-text text-sm font-medium">
          Description (optional)
        </label>
        <textarea
          id="course-description"
          rows={2}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          className="border-border bg-surface rounded-sm border px-3 py-2 text-sm"
        />
      </div>
      <div className="flex gap-2">
        <SubmitButton submitting={createCourse.isPending} className={primaryButtonClass}>
          Create course
        </SubmitButton>
        <button type="button" onClick={onDone} className={secondaryButtonClass}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** M20 §23: `/learning` — every course the user has, plus a way to start a new one. */
export function CourseList(): ReactElement {
  const coursesQuery = useInfiniteQuery(learningCoursesInfiniteQueryOptions());
  const [creating, setCreating] = useState(false);
  const courses = coursesQuery.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <h1>Learning</h1>
        {!creating && (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className={`${primaryButtonClass} inline-flex items-center gap-1.5`}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            New course
          </button>
        )}
      </div>

      {creating && <CourseCreateForm onDone={() => setCreating(false)} />}

      {coursesQuery.isPending && (
        <p aria-busy="true" className="text-text-muted text-sm">
          Loading courses…
        </p>
      )}

      {coursesQuery.isError && (
        <div className="border-border bg-surface flex flex-col items-center gap-3 rounded-md border border-dashed p-8 text-center">
          <AlertCircle className="text-danger h-8 w-8" aria-hidden="true" />
          <p role="alert" className="text-text-muted text-sm">
            Failed to load courses.
          </p>
          <button
            type="button"
            onClick={() => void coursesQuery.refetch()}
            className={secondaryButtonClass}
          >
            Retry
          </button>
        </div>
      )}

      {coursesQuery.isSuccess && courses.length === 0 && !creating && (
        <EmptyState
          icon={BookOpen}
          title="No courses yet. Create one to start turning a source into a course."
          action={
            <button type="button" onClick={() => setCreating(true)} className={primaryButtonClass}>
              Create your first course
            </button>
          }
        />
      )}

      {courses.length > 0 && (
        <ul className="flex flex-col gap-3">
          {courses.map((course) => (
            <li key={course.id}>
              <Link
                to="/learning/$courseId"
                params={{ courseId: course.id }}
                className="border-border bg-surface hover:bg-surface-sunken focus-visible:outline-accent flex items-center justify-between gap-3 rounded-md border p-3 text-sm focus-visible:outline focus-visible:outline-2"
              >
                <div className="min-w-0">
                  <p className="text-text truncate font-medium">{course.title}</p>
                  {course.description && (
                    <p className="text-text-muted truncate text-xs">{course.description}</p>
                  )}
                </div>
                <span className="text-text-muted shrink-0 text-xs">
                  {STATUS_LABEL[course.status] ?? course.status}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {coursesQuery.hasNextPage && (
        <button
          type="button"
          onClick={() => void coursesQuery.fetchNextPage()}
          disabled={coursesQuery.isFetchingNextPage}
          className={`${secondaryButtonClass} mt-4 self-center`}
        >
          {coursesQuery.isFetchingNextPage ? 'Loading…' : 'Load more'}
        </button>
      )}
    </>
  );
}
