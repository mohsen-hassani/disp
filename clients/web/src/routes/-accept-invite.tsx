import { zodResolver } from '@hookform/resolvers/zod';
import { type ReactElement, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import { acceptInvite } from '../auth/AuthProvider';
import { SubmitButton } from '../components/feedback/SubmitButton';
import { navigate } from '../lib/navigate';

// Router-ignored (leading `-`) — see -login.tsx's doc for why the page
// implementation lives outside the route file itself.

// Backend §10.3 (src/disp/core/auth/passwords.py: MIN_PASSWORD_LENGTH=12,
// MAX_PASSWORD_LENGTH=128). The "≠ the invited email" rule from §8.8 is
// NOT checked here: the invited email isn't known to an unauthenticated
// client before submission (no "look up an invite by token" endpoint
// exists), so that specific rule can only be enforced server-side — a
// 422 auth.password_policy response maps to the password field exactly
// like any other server-side validation failure.
const MIN_PASSWORD_LENGTH = 12;
const MAX_PASSWORD_LENGTH = 128;

const acceptInviteSchema = z
  .object({
    displayName: z.string().min(1, 'Display name is required').max(100),
    password: z
      .string()
      .min(MIN_PASSWORD_LENGTH, `Password must be at least ${MIN_PASSWORD_LENGTH} characters long.`)
      .max(MAX_PASSWORD_LENGTH, `Password must be at most ${MAX_PASSWORD_LENGTH} characters long.`),
    confirmPassword: z.string(),
  })
  .refine((values) => values.password === values.confirmPassword, {
    message: "Passwords don't match.",
    path: ['confirmPassword'],
  });
type AcceptInviteFormValues = z.infer<typeof acceptInviteSchema>;

// Advisory-only per §8.8 — never blocks submission, just a hint.
function passwordStrength(password: string): 'weak' | 'fair' | 'strong' {
  if (password.length < MIN_PASSWORD_LENGTH) {
    return 'weak';
  }
  const varietyCount = [/[a-z]/, /[A-Z]/, /\d/, /[^a-zA-Z0-9]/].filter((re) =>
    re.test(password),
  ).length;
  if (password.length >= 16 && varietyCount >= 3) {
    return 'strong';
  }
  return 'fair';
}

// Appendix D, verbatim.
const INVITE_NOT_FOUND_COPY = "We couldn't find that invitation. Check the link and try again.";
const INVITE_USED_COPY = 'This invitation has already been used. Try signing in instead.';
const INVITE_EXPIRED_COPY = 'This invitation has expired. Ask for a new one.';

type ScreenState = 'form' | 'not_found' | 'used' | 'expired';

export function AcceptInvitePage(): ReactElement {
  const token = new URLSearchParams(window.location.search).get('token');
  // No form is rendered for any of these states (§8.8) — a missing token
  // can never succeed, so show the not-found state immediately rather than
  // rendering a form that's guaranteed to fail on submit.
  const [screen, setScreen] = useState<ScreenState>(token ? 'form' : 'not_found');
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<AcceptInviteFormValues>({ resolver: zodResolver(acceptInviteSchema) });
  const password = watch('password') ?? '';

  const onSubmit = handleSubmit(async ({ displayName, password: pw }) => {
    if (!token) {
      setScreen('not_found');
      return;
    }
    setFormError(null);

    const result = await acceptInvite(token, displayName, pw);
    if (result.ok) {
      navigate('/');
      return;
    }

    const { problem } = result.error;
    switch (problem.code) {
      case 'auth.invite_not_found':
        setScreen('not_found');
        break;
      case 'auth.invite_used':
        setScreen('used');
        break;
      case 'auth.invite_expired':
        setScreen('expired');
        break;
      default:
        setFormError(problem.detail || 'Something went wrong. Please try again.');
    }
  });

  if (screen === 'not_found') {
    return (
      <main
        id="main-content"
        className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-4 py-8"
      >
        <h1 className="text-text text-xl font-semibold">Invitation not found</h1>
        <p className="text-text-muted mt-2 text-sm">{INVITE_NOT_FOUND_COPY}</p>
      </main>
    );
  }
  if (screen === 'used') {
    return (
      <main
        id="main-content"
        className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-4 py-8"
      >
        <h1 className="text-text text-xl font-semibold">Invitation already used</h1>
        <p className="text-text-muted mt-2 text-sm">{INVITE_USED_COPY}</p>
      </main>
    );
  }
  if (screen === 'expired') {
    return (
      <main
        id="main-content"
        className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-4 py-8"
      >
        <h1 className="text-text text-xl font-semibold">Invitation expired</h1>
        <p className="text-text-muted mt-2 text-sm">{INVITE_EXPIRED_COPY}</p>
      </main>
    );
  }

  return (
    <main
      id="main-content"
      className="mx-auto flex min-h-screen w-full max-w-sm flex-col justify-center px-4 py-8"
    >
      <h1 className="text-text text-xl font-semibold">Accept invitation</h1>
      <form
        onSubmit={(event) => void onSubmit(event)}
        noValidate
        className="mt-6 flex flex-col gap-4"
      >
        <div className="flex flex-col gap-1">
          <label htmlFor="invite-display-name" className="text-text text-sm font-medium">
            Display name
          </label>
          <input
            id="invite-display-name"
            type="text"
            autoComplete="name"
            aria-invalid={errors.displayName ? true : undefined}
            aria-describedby={errors.displayName ? 'invite-display-name-error' : undefined}
            {...register('displayName')}
          />
          {errors.displayName && (
            <p id="invite-display-name-error" role="alert" className="text-danger text-xs">
              {errors.displayName.message}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="invite-password" className="text-text text-sm font-medium">
            Password
          </label>
          <input
            id="invite-password"
            type="password"
            autoComplete="new-password"
            aria-invalid={errors.password ? true : undefined}
            aria-describedby={errors.password ? 'invite-password-error' : undefined}
            {...register('password')}
          />
          {errors.password && (
            <p id="invite-password-error" role="alert" className="text-danger text-xs">
              {errors.password.message}
            </p>
          )}
          {password.length > 0 && (
            <p aria-live="polite" className="text-text-muted text-xs">
              Password strength: {passwordStrength(password)}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="invite-confirm-password" className="text-text text-sm font-medium">
            Confirm password
          </label>
          <input
            id="invite-confirm-password"
            type="password"
            autoComplete="new-password"
            aria-invalid={errors.confirmPassword ? true : undefined}
            aria-describedby={errors.confirmPassword ? 'invite-confirm-password-error' : undefined}
            {...register('confirmPassword')}
          />
          {errors.confirmPassword && (
            <p id="invite-confirm-password-error" role="alert" className="text-danger text-xs">
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
          Accept invitation
        </SubmitButton>
      </form>
    </main>
  );
}
