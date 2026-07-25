import { zodResolver } from '@hookform/resolvers/zod';
import * as Dialog from '@radix-ui/react-dialog';
import * as Switch from '@radix-ui/react-switch';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy } from 'lucide-react';
import { type ReactElement, useEffect, useId, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { z } from 'zod';

import type { InviteOut } from '../api/generated';
import { authCreateInvite, authDeleteInvite } from '../api/generated';
import { parseProblem } from '../api/problem';
import { invitesQueryOptions } from '../api/queries';
import { qk } from '../api/queryKeys';
import { useToast } from '../components/feedback/ToastProvider';
import { cn } from '../lib/cn';
import { relativeTime } from '../lib/format';

// Router-ignored (leading `-`) — see -login.tsx's doc for why.

const createInviteSchema = z.object({
  email: z.string().min(1, 'Email is required').max(254).email('Enter a valid email address'),
  isAdmin: z.boolean(),
});
type CreateInviteFormValues = z.infer<typeof createInviteSchema>;

// Appendix D, DISP-renamed per this milestone's own naming note (the spec's
// literal draft copy says "MyStuff doesn't send email").
const INVITE_CREATED_NOTE = "Send this link to the person yourself — DISP doesn't send email.";
const USER_EXISTS_COPY = 'A user with this email address already exists.';
const INVITE_PENDING_COPY = 'A pending invite already exists for this email address.';

const dialogContentClass =
  'border-border bg-surface shadow-overlay fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4';
const buttonClass =
  'border-border text-text focus-visible:outline-accent rounded-sm border px-3 py-1.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2';
const primaryButtonClass =
  'bg-accent text-accent-text focus-visible:outline-accent rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60';

export function InvitesPage(): ReactElement {
  const invitesQuery = useQuery(invitesQueryOptions());
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [createOpen, setCreateOpen] = useState(false);
  const [formError, setFormError] = useState<string | undefined>();
  const [revokeTarget, setRevokeTarget] = useState<InviteOut | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  // §15.3: same discipline as the PAT reveal — the token/accept_url lives
  // only here, only while this dialog is open.
  const [revealed, setRevealed] = useState<{ email: string; acceptUrl: string } | null>(null);

  useEffect(() => {
    return () => setRevealed(null);
  }, []);

  const {
    register,
    control,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<CreateInviteFormValues>({
    resolver: zodResolver(createInviteSchema),
    defaultValues: { email: '', isAdmin: false },
  });

  const onCreateSubmit = handleSubmit(async (values) => {
    setFormError(undefined);
    const { data, error, response } = await authCreateInvite({
      body: { email: values.email, is_admin: values.isAdmin },
    });
    if (!response?.ok || !data) {
      const problem = parseProblem(response ?? new Response(null, { status: 0 }), error);
      if (problem.code === 'auth.user_exists') {
        setError('email', { message: USER_EXISTS_COPY });
      } else if (problem.code === 'auth.invite_pending') {
        setError('email', { message: INVITE_PENDING_COPY });
      } else {
        setFormError(problem.detail || 'Something went wrong. Please try again.');
      }
      return;
    }
    setCreateOpen(false);
    reset({ email: '', isAdmin: false });
    void queryClient.invalidateQueries({ queryKey: qk.auth.invites() });
    setRevealed({ email: data.email, acceptUrl: data.accept_url });
  });

  async function handleRevoke(target: InviteOut): Promise<void> {
    setRevokingId(target.id);
    const { response } = await authDeleteInvite({ path: { invite_id: target.id } });
    setRevokingId(null);
    if (response?.ok) {
      setRevokeTarget(null);
      void queryClient.invalidateQueries({ queryKey: qk.auth.invites() });
      showToast(`Invite to ${target.email} revoked.`);
    } else {
      showToast('Something went wrong. Please try again.', 'danger');
    }
  }

  return (
    <>
      <h1>Invitations</h1>

      <button
        type="button"
        onClick={() => setCreateOpen(true)}
        className={cn('mt-4', primaryButtonClass)}
      >
        Invite someone
      </button>

      {invitesQuery.isPending && <p aria-busy="true">Loading…</p>}
      {invitesQuery.isError && <p role="alert">Failed to load invites.</p>}
      {invitesQuery.data && (
        <table className="mt-4 w-full text-left text-sm">
          <thead>
            <tr className="border-border border-b">
              <th className="py-2 font-medium">Email</th>
              <th className="py-2 font-medium">Admin</th>
              <th className="py-2 font-medium">Expires</th>
              <th className="py-2 font-medium">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {invitesQuery.data.map((invite) => (
              <tr key={invite.id} className="border-border border-b">
                <td className="py-2">{invite.email}</td>
                <td className="py-2">{invite.is_admin ? 'Yes' : 'No'}</td>
                <td className="py-2">{relativeTime(invite.expires_at)}</td>
                <td className="py-2 text-right">
                  <button
                    type="button"
                    onClick={() => setRevokeTarget(invite)}
                    disabled={revokingId === invite.id}
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
      {invitesQuery.data?.length === 0 && (
        <p className="text-text-muted mt-4 text-sm">No pending invites.</p>
      )}

      <Dialog.Root
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open);
          if (!open) {
            setFormError(undefined);
            reset({ email: '', isAdmin: false });
          }
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/40" />
          <Dialog.Content aria-labelledby="create-invite-title" className={dialogContentClass}>
            <Dialog.Title id="create-invite-title" className="text-text mb-3 text-sm font-medium">
              Invite someone
            </Dialog.Title>
            <form
              onSubmit={(event) => void onCreateSubmit(event)}
              noValidate
              className="flex flex-col gap-4"
            >
              <div className="flex flex-col gap-1">
                <label htmlFor="invite-email" className="text-text text-sm font-medium">
                  Email
                </label>
                <input
                  id="invite-email"
                  type="email"
                  aria-invalid={errors.email ? true : undefined}
                  aria-describedby={errors.email ? 'invite-email-error' : undefined}
                  {...register('email')}
                />
                {errors.email && (
                  <p id="invite-email-error" role="alert" className="text-danger text-xs">
                    {errors.email.message}
                  </p>
                )}
              </div>

              <div className="flex items-center gap-2">
                <Controller
                  name="isAdmin"
                  control={control}
                  render={({ field }) => (
                    <Switch.Root
                      id="invite-is-admin"
                      checked={field.value}
                      onCheckedChange={field.onChange}
                      className="bg-surface-sunken data-[state=checked]:bg-accent focus-visible:outline-accent relative h-6 w-10 rounded-full transition-colors duration-fast focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 motion-reduce:transition-none"
                    >
                      <Switch.Thumb className="bg-surface block h-5 w-5 translate-x-0.5 rounded-full transition-transform duration-fast data-[state=checked]:translate-x-[18px] motion-reduce:transition-none" />
                    </Switch.Root>
                  )}
                />
                <label htmlFor="invite-is-admin" className="text-text text-sm font-medium">
                  Grant admin access
                </label>
              </div>

              {formError && (
                <p role="alert" className="text-danger text-sm">
                  {formError}
                </p>
              )}

              <button
                type="submit"
                disabled={isSubmitting}
                className={cn('self-start', primaryButtonClass)}
              >
                {isSubmitting ? 'Sending…' : 'Create invite'}
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
          <Dialog.Content aria-labelledby="revoke-invite-title" className={dialogContentClass}>
            <Dialog.Title id="revoke-invite-title" className="text-text mb-2 text-sm font-medium">
              Revoke invite to &quot;{revokeTarget?.email}&quot;?
            </Dialog.Title>
            <p className="text-text-muted mb-4 text-sm">This can&apos;t be undone.</p>
            <div className="flex justify-end gap-2">
              <Dialog.Close className={buttonClass}>Cancel</Dialog.Close>
              <button
                type="button"
                onClick={() => revokeTarget && void handleRevoke(revokeTarget)}
                disabled={revokingId !== null}
                className="bg-danger text-accent-text rounded-sm px-3 py-1.5 text-sm font-medium disabled:opacity-60"
              >
                Revoke invite
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}

interface RevealDialogProps {
  revealed: { email: string; acceptUrl: string } | null;
  onDismiss: () => void;
}

// §15.3: same one-time-reveal discipline as the PAT dialog — explicit
// dismissal only, no X, Escape/outside-click suppressed.
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
            Invite for {revealed?.email} created
          </Dialog.Title>
          <p className="text-text-muted mb-2 text-sm">{INVITE_CREATED_NOTE}</p>
          <div className="border-border bg-surface-sunken mb-4 flex items-center gap-2 rounded-sm border p-2">
            <code className="flex-1 overflow-x-auto text-sm break-all">{revealed?.acceptUrl}</code>
            <button
              type="button"
              aria-label="Copy invite link"
              onClick={() => {
                if (revealed) {
                  void navigator.clipboard.writeText(revealed.acceptUrl);
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
