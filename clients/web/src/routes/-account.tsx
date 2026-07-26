import { zodResolver } from '@hookform/resolvers/zod';
import { useQuery } from '@tanstack/react-query';
import { type ReactElement, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import { authChangePassword } from '../api/generated';
import { parseProblem } from '../api/problem';
import { meQueryOptions } from '../api/queries';
import { SubmitButton } from '../components/feedback/SubmitButton';
import { useToast } from '../components/feedback/ToastProvider';

// Router-ignored (leading `-`) — see -login.tsx's doc for why the page
// implementation lives outside the route file itself.

// Backend §10.3 (src/disp/core/auth/passwords.py: MIN_PASSWORD_LENGTH=12,
// MAX_PASSWORD_LENGTH=128, and — unlike accept-invite, which can't check
// this client-side because the invited email isn't known pre-submission —
// this screen already knows the signed-in user's email, so the "password
// != email" rule is enforced here too, not left entirely to the server.
const MIN_PASSWORD_LENGTH = 12;
const MAX_PASSWORD_LENGTH = 128;

function passwordSchema(email: string) {
  return z
    .object({
      currentPassword: z.string().min(1, 'Current password is required'),
      newPassword: z
        .string()
        .min(
          MIN_PASSWORD_LENGTH,
          `Password must be at least ${MIN_PASSWORD_LENGTH} characters long.`,
        )
        .max(
          MAX_PASSWORD_LENGTH,
          `Password must be at most ${MAX_PASSWORD_LENGTH} characters long.`,
        )
        .refine((value) => value.toLowerCase() !== email.toLowerCase(), {
          message: 'Password must not be the same as your email address.',
        }),
      confirmPassword: z.string(),
    })
    .refine((values) => values.newPassword === values.confirmPassword, {
      message: "Passwords don't match.",
      path: ['confirmPassword'],
    });
}
type PasswordFormValues = z.infer<ReturnType<typeof passwordSchema>>;

const CURRENT_PASSWORD_INCORRECT_COPY = "That password doesn't match your current one.";
const PASSWORD_CHANGED_COPY = "Password changed. You've been signed out of your other sessions.";

export function AccountPage(): ReactElement {
  const meQuery = useQuery(meQueryOptions());
  const { showToast } = useToast();
  const [formError, setFormError] = useState<string | undefined>();
  const email = meQuery.data?.email ?? '';
  const schema = useMemo(() => passwordSchema(email), [email]);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<PasswordFormValues>({ resolver: zodResolver(schema) });

  // §15.1: browser sessions are always `auth_method: "password"` in
  // practice (§8.9: the browser never authenticates with a PAT) — this
  // check exists so the copy stays truthful about the server's actual
  // rule rather than assuming it, per the milestone's own instruction.
  const isPatSession = meQuery.data?.auth_method === 'api_token';

  const onSubmit = handleSubmit(async ({ currentPassword, newPassword }) => {
    setFormError(undefined);
    const { error, response } = await authChangePassword({
      body: { current_password: currentPassword, new_password: newPassword },
    });
    if (!response?.ok) {
      const problem = parseProblem(response ?? new Response(null, { status: 0 }), error);
      if (problem.status === 401) {
        setError('currentPassword', { message: CURRENT_PASSWORD_INCORRECT_COPY });
      } else if (problem.code === 'auth.password_policy') {
        setError('newPassword', { message: problem.detail });
      } else if (problem.status === 429) {
        setFormError('Too many attempts. Please try again later.');
      } else {
        setFormError(problem.detail || 'Something went wrong. Please try again.');
      }
      return;
    }
    reset();
    showToast(PASSWORD_CHANGED_COPY, 'success');
  });

  return (
    <>
      <h1>Account</h1>
      {meQuery.data && (
        <dl className="mt-4 grid max-w-md grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-text-muted">Display name</dt>
          <dd className="text-text">{meQuery.data.display_name}</dd>
          <dt className="text-text-muted">Email</dt>
          <dd className="text-text">{meQuery.data.email}</dd>
          <dt className="text-text-muted">Role</dt>
          <dd className="text-text">{meQuery.data.is_admin ? 'Administrator' : 'Member'}</dd>
        </dl>
      )}

      <h2 className="mt-8 text-base font-medium">Change password</h2>
      {isPatSession ? (
        <p className="text-text-muted mt-2 text-sm">
          This form is unavailable when signed in with an API token — sign in with your password
          instead to change it.
        </p>
      ) : (
        <form
          onSubmit={(event) => void onSubmit(event)}
          noValidate
          className="mt-2 flex max-w-md flex-col gap-4"
        >
          <div className="flex flex-col gap-1">
            <label htmlFor="current-password" className="text-text text-sm font-medium">
              Current password
            </label>
            <input
              id="current-password"
              type="password"
              autoComplete="current-password"
              aria-invalid={errors.currentPassword ? true : undefined}
              aria-describedby={errors.currentPassword ? 'current-password-error' : undefined}
              {...register('currentPassword')}
            />
            {errors.currentPassword && (
              <p id="current-password-error" role="alert" className="text-danger text-xs">
                {errors.currentPassword.message}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="new-password" className="text-text text-sm font-medium">
              New password
            </label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              aria-invalid={errors.newPassword ? true : undefined}
              aria-describedby={errors.newPassword ? 'new-password-error' : undefined}
              {...register('newPassword')}
            />
            {errors.newPassword && (
              <p id="new-password-error" role="alert" className="text-danger text-xs">
                {errors.newPassword.message}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="confirm-password" className="text-text text-sm font-medium">
              Confirm new password
            </label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              aria-invalid={errors.confirmPassword ? true : undefined}
              aria-describedby={errors.confirmPassword ? 'confirm-password-error' : undefined}
              {...register('confirmPassword')}
            />
            {errors.confirmPassword && (
              <p id="confirm-password-error" role="alert" className="text-danger text-xs">
                {errors.confirmPassword.message}
              </p>
            )}
          </div>

          {formError && (
            <p role="alert" className="text-danger text-sm">
              {formError}
            </p>
          )}

          <SubmitButton
            submitting={isSubmitting}
            className="bg-accent text-accent-text focus-visible:outline-accent self-start rounded-sm px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60"
          >
            Change password
          </SubmitButton>
        </form>
      )}
    </>
  );
}
