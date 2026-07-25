import { zodResolver } from '@hookform/resolvers/zod';
import * as Dialog from '@radix-ui/react-dialog';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy } from 'lucide-react';
import { type ReactElement, useEffect, useId, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import type { ApiTokenOut } from '../api/generated';
import { authCreateToken, authRevokeToken } from '../api/generated';
import { parseProblem } from '../api/problem';
import { tokensQueryOptions } from '../api/queries';
import { qk } from '../api/queryKeys';
import { useToast } from '../components/feedback/ToastProvider';
import { cn } from '../lib/cn';
import { dateTime, relativeTime } from '../lib/format';

// Router-ignored (leading `-`) — see -login.tsx's doc for why.

const NAME_MAX_LENGTH = 64;
const createTokenSchema = z.object({
  name: z
    .string()
    .min(1, 'Name is required')
    .max(NAME_MAX_LENGTH, `Name must be at most ${NAME_MAX_LENGTH} characters long.`),
  expiresInDays: z
    .string()
    .optional()
    .refine((value) => !value || /^\d+$/.test(value), 'Enter a whole number of days.'),
});
type CreateTokenFormValues = z.infer<typeof createTokenSchema>;

const dialogContentClass =
  'border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4';
const buttonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2';
const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

export function TokensPage(): ReactElement {
  const tokensQuery = useQuery(tokensQueryOptions());
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | undefined>();
  const [revokeTarget, setRevokeTarget] = useState<ApiTokenOut | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  // §15.2: the plaintext lives here, and only here, for exactly as long as
  // the reveal dialog is open. Never written to a query cache, never held
  // by a mutation object past the moment it's read.
  const [revealed, setRevealed] = useState<{ name: string; token: string } | null>(null);

  useEffect(() => {
    return () => setRevealed(null);
  }, []);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CreateTokenFormValues>({ resolver: zodResolver(createTokenSchema) });

  const onCreateSubmit = handleSubmit(async (values) => {
    setCreateError(undefined);
    const expiresInDays = values.expiresInDays ? Number(values.expiresInDays) : null;
    const { data, error, response } = await authCreateToken({
      body: { name: values.name, expires_in_days: expiresInDays },
    });
    if (!response?.ok || !data) {
      const problem = parseProblem(response ?? new Response(null, { status: 0 }), error);
      setCreateError(problem.detail || 'Something went wrong. Please try again.');
      return;
    }
    setCreateOpen(false);
    reset();
    void queryClient.invalidateQueries({ queryKey: qk.auth.tokens() });
    // The reveal dialog reads only these two fields — `data` (and its
    // `token`) is discarded immediately after, never retained.
    setRevealed({ name: data.name, token: data.token });
  });

  async function handleRevoke(target: ApiTokenOut): Promise<void> {
    setRevokingId(target.id);
    const { response } = await authRevokeToken({ path: { token_id: target.id } });
    setRevokingId(null);
    if (response?.ok) {
      setRevokeTarget(null);
      void queryClient.invalidateQueries({ queryKey: qk.auth.tokens() });
      showToast(`"${target.name}" revoked.`);
    } else {
      showToast('Something went wrong. Please try again.', 'danger');
    }
  }

  return (
    <>
      <h1>API tokens</h1>
      <p className="text-text-muted mt-2 max-w-prose text-sm">
        Personal access tokens for the <code>disp</code> CLI — run <code>disp login</code> to
        authenticate it, or pass one directly with <code>Authorization: Bearer &lt;token&gt;</code>.
        See the repo README for the full CLI quickstart.
      </p>

      <button
        type="button"
        onClick={() => setCreateOpen(true)}
        className={cn('mt-4', primaryButtonClass)}
      >
        Create token
      </button>

      {tokensQuery.isPending && <p aria-busy="true">Loading…</p>}
      {tokensQuery.isError && <p role="alert">Failed to load API tokens.</p>}
      {tokensQuery.data && (
        <table className="mt-4 w-full text-left text-sm">
          <thead>
            <tr className="border-border border-b">
              <th className="py-2 font-medium">Name</th>
              <th className="py-2 font-medium">Prefix</th>
              <th className="py-2 font-medium">Created</th>
              <th className="py-2 font-medium">Last used</th>
              <th className="py-2 font-medium">Expires</th>
              <th className="py-2 font-medium">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {tokensQuery.data.map((token) => (
              <tr key={token.id} className="border-border border-b">
                <td className="py-2">{token.name}</td>
                <td className="text-text-muted py-2 font-mono">{token.token_prefix}…</td>
                <td className="py-2">{dateTime(token.created_at)}</td>
                <td className="py-2">
                  {token.last_used_at ? relativeTime(token.last_used_at) : 'Never'}
                </td>
                <td className="py-2">
                  {token.expires_at ? relativeTime(token.expires_at) : 'Never'}
                </td>
                <td className="py-2 text-right">
                  <button
                    type="button"
                    onClick={() => setRevokeTarget(token)}
                    disabled={revokingId === token.id}
                    className={buttonClass}
                  >
                    Revoke
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {tokensQuery.data?.length === 0 && (
        <p className="text-text-muted mt-4 text-sm">No API tokens yet.</p>
      )}

      <Dialog.Root
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open);
          if (!open) {
            setCreateError(undefined);
            reset();
          }
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/40" />
          <Dialog.Content aria-labelledby="create-token-title" className={dialogContentClass}>
            <Dialog.Title id="create-token-title" className="text-text mb-3 text-sm font-medium">
              Create token
            </Dialog.Title>
            <form
              onSubmit={(event) => void onCreateSubmit(event)}
              noValidate
              className="flex flex-col gap-4"
            >
              <div className="flex flex-col gap-1">
                <label htmlFor="token-name" className="text-text text-sm font-medium">
                  Name
                </label>
                <input
                  id="token-name"
                  type="text"
                  aria-invalid={errors.name ? true : undefined}
                  aria-describedby={errors.name ? 'token-name-error' : undefined}
                  {...register('name')}
                />
                {errors.name && (
                  <p id="token-name-error" role="alert" className="text-danger text-xs">
                    {errors.name.message}
                  </p>
                )}
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="token-expires" className="text-text text-sm font-medium">
                  Expires in (days, optional)
                </label>
                <input
                  id="token-expires"
                  type="number"
                  min={1}
                  step={1}
                  aria-invalid={errors.expiresInDays ? true : undefined}
                  aria-describedby={errors.expiresInDays ? 'token-expires-error' : undefined}
                  {...register('expiresInDays')}
                />
                {errors.expiresInDays && (
                  <p id="token-expires-error" role="alert" className="text-danger text-xs">
                    {errors.expiresInDays.message}
                  </p>
                )}
              </div>
              {createError && (
                <p role="alert" className="text-danger text-sm">
                  {createError}
                </p>
              )}
              <button
                type="submit"
                disabled={isSubmitting}
                className={cn('self-start', primaryButtonClass)}
              >
                {isSubmitting ? 'Creating…' : 'Create token'}
              </button>
            </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <RevealDialog revealed={revealed} onDismiss={() => setRevealed(null)} />

      <Dialog.Root
        open={revokeTarget !== null}
        onOpenChange={(open) => !open && setRevokeTarget(null)}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/40" />
          <Dialog.Content aria-labelledby="revoke-token-title" className={dialogContentClass}>
            <Dialog.Title id="revoke-token-title" className="text-text mb-2 text-sm font-medium">
              Revoke &quot;{revokeTarget?.name}&quot;?
            </Dialog.Title>
            <p className="text-text-muted mb-4 text-sm">
              The <code>disp</code> CLI will no longer be able to authenticate with this token. This
              can&apos;t be undone.
            </p>
            <div className="flex justify-end gap-2">
              <Dialog.Close className={buttonClass}>Cancel</Dialog.Close>
              <button
                type="button"
                onClick={() => revokeTarget && void handleRevoke(revokeTarget)}
                disabled={revokingId !== null}
                className="bg-danger text-accent-text rounded-sm px-3 py-1.5 text-sm font-medium disabled:opacity-60"
              >
                Revoke token
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}

interface RevealDialogProps {
  revealed: { name: string; token: string } | null;
  onDismiss: () => void;
}

// §15.2: dismissible only via the explicit "I've saved it" button — no X,
// and Escape/outside-click are suppressed, so a plaintext this sensitive
// can't be dropped by an accidental keystroke or misclick.
function RevealDialog({ revealed, onDismiss }: RevealDialogProps): ReactElement {
  const titleId = useId();
  const [copied, setCopied] = useState(false);

  return (
    <Dialog.Root open={revealed !== null}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content
          aria-labelledby={titleId}
          onEscapeKeyDown={(event) => event.preventDefault()}
          onPointerDownOutside={(event) => event.preventDefault()}
          onInteractOutside={(event) => event.preventDefault()}
          className={dialogContentClass}
        >
          <Dialog.Title id={titleId} className="text-text mb-2 text-sm font-medium">
            &quot;{revealed?.name}&quot; created
          </Dialog.Title>
          <p className="text-danger mb-2 text-sm">
            Copy this token now. You won&apos;t be able to see it again.
          </p>
          <div className="border-border bg-surface-sunken mb-4 flex items-center gap-2 rounded-sm border p-2">
            <code className="flex-1 overflow-x-auto text-sm break-all">{revealed?.token}</code>
            <button
              type="button"
              aria-label="Copy token"
              onClick={() => {
                if (revealed) {
                  void navigator.clipboard.writeText(revealed.token);
                  setCopied(true);
                }
              }}
              className="text-text-muted focus-visible:outline-accent shrink-0 rounded-sm p-1 focus-visible:outline focus-visible:outline-2"
            >
              <Copy className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          {copied && (
            <p aria-live="polite" className="text-text-muted mb-2 text-xs">
              Copied.
            </p>
          )}
          <button
            type="button"
            onClick={() => {
              setCopied(false);
              onDismiss();
            }}
            className={primaryButtonClass}
          >
            I&apos;ve saved it
          </button>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
