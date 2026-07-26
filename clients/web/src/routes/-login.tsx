import { zodResolver } from '@hookform/resolvers/zod';
import { type ReactElement, useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

import { login } from '../auth/AuthProvider';
import { RevokedBanner } from '../components/feedback/RevokedBanner';
import { SubmitButton } from '../components/feedback/SubmitButton';
import { navigate } from '../lib/navigate';

// Router-ignored (leading `-`, see eslint.config.js/router.config's
// `routeFileIgnorePrefix`) — the page implementation lives here rather than
// in `login.tsx` itself so that route file can stay a bare `Route` export.
// @tanstack/router-plugin's `autoCodeSplitting` only splits a route file
// that exports *nothing else*; any other export (this component,
// `resolveNextPath`, needed by tests) makes it bail on splitting the whole
// file, defeating WEB-SPEC §9's "every route is a lazy chunk" requirement.

// WEB-SPEC §8.7 open-redirect defense: `next` is only honored when it's a
// same-origin relative path starting with a single `/` — an absolute URL
// (https://evil.example) or a protocol-relative one (//evil.example, which
// a browser resolves exactly like https://evil.example) falls back to `/`.
export function resolveNextPath(rawNext: string | null): string {
  if (rawNext && rawNext.startsWith('/') && !rawNext.startsWith('//')) {
    return rawNext;
  }
  return '/';
}

// §19.2's email rule (≤254, valid format) mirrors backend §10.4. Password
// has no client-side policy check here — login isn't where the password
// policy applies, only account creation/change (§8.8, M07).
const loginSchema = z.object({
  email: z.string().min(1, 'Email is required').max(254).email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
});
type LoginFormValues = z.infer<typeof loginSchema>;

// Appendix D, verbatim. §8.7: the client MUST NOT distinguish unknown-email
// from wrong-password — both map to auth.invalid_credentials from the
// backend (confirmed: src/disp/core/auth/routes.py uses this single code
// for both), so there's exactly one branch here, not two.
const INVALID_CREDENTIALS_COPY = "That email and password don't match. Please try again.";
const ACCOUNT_DISABLED_COPY = 'This account has been deactivated. Contact your administrator.';
const DEFAULT_RETRY_AFTER_SECONDS = 30;

export function LoginPage(): ReactElement {
  const next = resolveNextPath(new URLSearchParams(window.location.search).get('next'));
  const [formError, setFormError] = useState<string | null>(null);
  const [retryAfter, setRetryAfter] = useState(0);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) });

  useEffect(() => {
    if (retryAfter <= 0) {
      return;
    }
    const timer = setInterval(() => {
      setRetryAfter((seconds) => Math.max(0, seconds - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [retryAfter]);

  const disabled = isSubmitting || retryAfter > 0;

  const onSubmit = handleSubmit(async ({ email, password }) => {
    if (disabled) {
      // Belt-and-braces: the submit button is disabled during the
      // Retry-After countdown, but a native Enter-key submit can still fire
      // — double-submit, including during a 429 cooldown, must be
      // impossible.
      return;
    }
    setFormError(null);

    const result = await login(email, password);
    if (result.ok) {
      navigate(next);
      return;
    }

    const { problem, retryAfterSeconds } = result.error;
    if (problem.code === 'auth.invalid_credentials') {
      setFormError(INVALID_CREDENTIALS_COPY);
    } else if (problem.code === 'auth.account_disabled') {
      setFormError(ACCOUNT_DISABLED_COPY);
    } else if (problem.status === 429) {
      setRetryAfter(retryAfterSeconds ?? DEFAULT_RETRY_AFTER_SECONDS);
    } else {
      setFormError(problem.detail || 'Something went wrong. Please try again.');
    }
  });

  return (
    <main id="main-content">
      <RevokedBanner />
      <h1>Sign in</h1>
      <form onSubmit={(event) => void onSubmit(event)} noValidate>
        <div>
          <label htmlFor="login-email">Email</label>
          <input
            id="login-email"
            type="email"
            autoComplete="username"
            aria-invalid={errors.email ? true : undefined}
            aria-describedby={errors.email ? 'login-email-error' : undefined}
            {...register('email')}
          />
          {errors.email && (
            <p id="login-email-error" role="alert">
              {errors.email.message}
            </p>
          )}
        </div>

        <div>
          <label htmlFor="login-password">Password</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            aria-invalid={errors.password ? true : undefined}
            aria-describedby={errors.password ? 'login-password-error' : undefined}
            {...register('password')}
          />
          {errors.password && (
            <p id="login-password-error" role="alert">
              {errors.password.message}
            </p>
          )}
        </div>

        {formError && <p role="alert">{formError}</p>}

        {retryAfter > 0 ? (
          <button type="submit" disabled>
            {`Try again in ${retryAfter}s`}
          </button>
        ) : (
          <SubmitButton submitting={isSubmitting} className="">
            Sign in
          </SubmitButton>
        )}
      </form>

      {/* No "remember me" — the 30-day refresh cookie is the only
          persistence. No password-reset flow exists in this backend. */}
      <p>Forgot your password? Ask your administrator to reset it.</p>
    </main>
  );
}
