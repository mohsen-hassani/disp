import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from '@tanstack/react-router';
import {
  BarChart3,
  FileText,
  ListChecks,
  MessageSquare,
  NotebookPen,
  Plus,
  RefreshCw,
} from 'lucide-react';
import { type FormEvent, type ReactElement, useCallback, useState } from 'react';

import type { JobOut } from '../../api/generated';
import {
  learningCourseQueryOptions,
  learningProgressQueryOptions,
  learningSourcesQueryOptions,
  learningWeakPointsQueryOptions,
} from '../../api/queries';
import { useLearningJob } from '../../hooks/useLearningJob';
import { SubmitButton } from '../feedback/SubmitButton';
import { useToast } from '../feedback/ToastProvider';
import {
  describeLearningError,
  useCreateSource,
  useDeleteSource,
  useGeneratePath,
  useIndexCourse,
} from './useLearningMutations';

const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';
const secondaryButtonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

const TITLE_MAX_LENGTH = 200;

const CONTENT_TYPES = [
  { value: 'markdown', label: 'Markdown' },
  { value: 'html', label: 'HTML' },
  { value: 'plain_text', label: 'Plain text' },
  { value: 'pdf', label: 'PDF' },
  { value: 'srt', label: 'Subtitles (SRT)' },
];

const FILE_CONTENT_TYPES = new Set(['pdf']);

/** M20 §16's job `error_code`s (`_map_index_error_code`/its `path.py` counterpart), for a settled-job toast. */
function describeJobFailure(job: JobOut): string {
  if (job.error_code === 'modules.learning.llm_unavailable') {
    return 'AI features are temporarily unavailable. Try again shortly.';
  }
  if (job.error_code === 'modules.learning.llm_refused') {
    return 'The AI declined to process this course. Try adjusting the source content.';
  }
  return 'The job failed. Please try again.';
}

interface CourseDetailPageProps {
  courseId: string;
}

function SourceAddForm({
  courseId,
  onDone,
}: {
  courseId: string;
  onDone: () => void;
}): ReactElement {
  const [title, setTitle] = useState('');
  const [contentType, setContentType] = useState('markdown');
  const [rawText, setRawText] = useState('');
  const [file, setFile] = useState<File | undefined>(undefined);
  const { showToast } = useToast();
  const createSource = useCreateSource();
  const needsFile = FILE_CONTENT_TYPES.has(contentType);

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    createSource.mutate(
      {
        courseId,
        title,
        contentType,
        file: needsFile ? file : undefined,
        rawText: needsFile ? undefined : rawText,
      },
      {
        onSuccess: () => {
          showToast('Source added.', 'success');
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
        <label htmlFor="source-title" className="text-text text-sm font-medium">
          Title
        </label>
        <input
          id="source-title"
          type="text"
          required
          maxLength={TITLE_MAX_LENGTH}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          className="border-border bg-surface rounded-sm border px-3 py-2 text-sm"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor="source-content-type" className="text-text text-sm font-medium">
          Type
        </label>
        <select
          id="source-content-type"
          value={contentType}
          onChange={(event) => setContentType(event.target.value)}
          className="border-border bg-surface rounded-sm border px-3 py-2 text-sm"
        >
          {CONTENT_TYPES.map((ct) => (
            <option key={ct.value} value={ct.value}>
              {ct.label}
            </option>
          ))}
        </select>
      </div>
      {needsFile ? (
        <div className="flex flex-col gap-1">
          <label htmlFor="source-file" className="text-text text-sm font-medium">
            File
          </label>
          <input
            id="source-file"
            type="file"
            required
            onChange={(event) => setFile(event.target.files?.[0])}
          />
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          <label htmlFor="source-raw-text" className="text-text text-sm font-medium">
            Content
          </label>
          <textarea
            id="source-raw-text"
            required
            rows={8}
            value={rawText}
            onChange={(event) => setRawText(event.target.value)}
            className="border-border bg-surface rounded-sm border px-3 py-2 font-mono text-sm"
          />
        </div>
      )}
      <div className="flex gap-2">
        <SubmitButton submitting={createSource.isPending} className={primaryButtonClass}>
          Add source
        </SubmitButton>
        <button type="button" onClick={onDone} className={secondaryButtonClass}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** M20 §23: `/learning/$courseId` — sources, indexing status, and the way into path/chat/notes. */
export function CourseDetailPage({ courseId }: CourseDetailPageProps): ReactElement {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [addingSource, setAddingSource] = useState(false);
  const [jobId, setJobId] = useState<string | undefined>(undefined);

  const courseQuery = useQuery(learningCourseQueryOptions(courseId));
  const sourcesQuery = useQuery(learningSourcesQueryOptions(courseId));
  const progressQuery = useQuery(learningProgressQueryOptions(courseId));
  const weakPointsQuery = useQuery(learningWeakPointsQueryOptions(courseId));
  const handleJobSettled = useCallback(
    (settledJob: JobOut) => {
      if (settledJob.status === 'failed') {
        showToast(describeJobFailure(settledJob), 'error');
      }
    },
    [showToast],
  );
  const job = useLearningJob(jobId, courseId, handleJobSettled);

  const indexCourse = useIndexCourse();
  const generatePath = useGeneratePath();
  const deleteSource = useDeleteSource();

  const course = courseQuery.data;
  const sources = sourcesQuery.data ?? [];
  const progress = progressQuery.data;
  const weakPoints = weakPointsQuery.data ?? [];
  const isIndexing = course?.status === 'indexing' || job.data?.status === 'running';

  if (courseQuery.isPending) {
    return <p aria-busy="true">Loading…</p>;
  }
  if (courseQuery.isError || !course) {
    return <p role="alert">Failed to load the course.</p>;
  }

  function handleIndex(): void {
    indexCourse.mutate(courseId, {
      onSuccess: (data) => {
        setJobId(data.id);
        showToast('Indexing started.', 'success');
      },
      onError: (error) => showToast(describeLearningError(error), 'error'),
    });
  }

  function handleGeneratePath(): void {
    generatePath.mutate(courseId, {
      onSuccess: (data) => {
        setJobId(data.id);
        showToast('Generating a learning path…', 'success');
        void navigate({ to: '/learning/$courseId/path', params: { courseId } });
      },
      onError: (error) => showToast(describeLearningError(error), 'error'),
    });
  }

  return (
    <>
      <h1 className="mb-1">{course.title}</h1>
      {course.description && <p className="text-text-muted mb-4 text-sm">{course.description}</p>}

      <div className="mb-6 flex flex-wrap gap-2">
        <Link
          to="/learning/$courseId/path"
          params={{ courseId }}
          className={`${secondaryButtonClass} inline-flex items-center gap-1.5`}
        >
          <ListChecks className="h-4 w-4" aria-hidden="true" />
          Learning path
        </Link>
        <Link
          to="/learning/$courseId/chat"
          params={{ courseId }}
          className={`${secondaryButtonClass} inline-flex items-center gap-1.5`}
        >
          <MessageSquare className="h-4 w-4" aria-hidden="true" />
          Chat
        </Link>
        <Link
          to="/learning/$courseId/notes"
          params={{ courseId }}
          className={`${secondaryButtonClass} inline-flex items-center gap-1.5`}
        >
          <NotebookPen className="h-4 w-4" aria-hidden="true" />
          Notes
        </Link>
      </div>

      {progress && (
        <div className="border-border bg-surface mb-6 rounded-md border p-4">
          <h2 className="mb-2 inline-flex items-center gap-1.5 text-sm font-medium">
            <BarChart3 className="h-4 w-4" aria-hidden="true" />
            Progress
          </h2>
          <p className="text-text-muted text-sm">
            {progress.completed} / {progress.total} lessons completed
          </p>
          {weakPoints.length > 0 && (
            <div className="mt-2">
              <p className="text-text-muted text-xs font-medium">Weakest topics</p>
              <ul className="mt-1 flex flex-wrap gap-1.5">
                {weakPoints.map((wp) => (
                  <li
                    key={wp.topic_tag_id}
                    className="border-border bg-surface-sunken rounded-full border px-2 py-0.5 text-xs"
                  >
                    {wp.tag_name}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="mb-4 flex items-center justify-between">
        <h2 className="inline-flex items-center gap-1.5 text-sm font-medium">
          <FileText className="h-4 w-4" aria-hidden="true" />
          Sources
        </h2>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleIndex}
            disabled={sources.length === 0 || isIndexing}
            className={`${secondaryButtonClass} inline-flex items-center gap-1.5`}
          >
            <RefreshCw
              className={`h-4 w-4 ${isIndexing ? 'animate-spin' : ''}`}
              aria-hidden="true"
            />
            {isIndexing ? 'Indexing…' : 'Index course'}
          </button>
          {course.status === 'active' && (
            <button
              type="button"
              onClick={handleGeneratePath}
              disabled={generatePath.isPending}
              className={secondaryButtonClass}
            >
              Generate path
            </button>
          )}
          {!addingSource && (
            <button
              type="button"
              onClick={() => setAddingSource(true)}
              className={`${primaryButtonClass} inline-flex items-center gap-1.5`}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add source
            </button>
          )}
        </div>
      </div>

      {addingSource && <SourceAddForm courseId={courseId} onDone={() => setAddingSource(false)} />}

      {sources.length === 0 ? (
        <p className="text-text-muted text-sm">
          No sources yet. Add one, then index the course to build its learning path.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {sources.map((source) => (
            <li
              key={source.id}
              className="border-border bg-surface flex items-center justify-between gap-3 rounded-md border p-3 text-sm"
            >
              <div className="min-w-0">
                <p className="text-text truncate font-medium">{source.title}</p>
                <p className="text-text-muted text-xs">{source.content_type}</p>
              </div>
              <button
                type="button"
                onClick={() =>
                  deleteSource.mutate(
                    { sourceId: source.id, courseId },
                    { onError: (error) => showToast(describeLearningError(error), 'error') },
                  )
                }
                disabled={deleteSource.isPending}
                className="text-danger text-xs font-medium"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
