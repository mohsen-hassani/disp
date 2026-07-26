import * as Toast from '@radix-ui/react-toast';
import { CheckCircle2, Info, XCircle } from 'lucide-react';
import {
  type ReactElement,
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useState,
} from 'react';

import { cn } from '../../lib/cn';

type ToastVariant = 'success' | 'error' | 'info';

// WEB-SPEC §20.1.
const VARIANT_DURATIONS: Record<ToastVariant, number> = {
  success: 4000,
  error: 8000,
  info: 5000,
};

const VARIANT_ICON: Record<ToastVariant, typeof CheckCircle2> = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
};

// §21 A8: status is never colour-alone — the icon (and the message text
// itself) carries the meaning independently of the border/icon colour.
const VARIANT_CLASS: Record<ToastVariant, string> = {
  success: 'border-success text-success',
  error: 'border-danger text-danger',
  info: 'border-border text-text',
};

// Max concurrent toasts (§20.1) — a 4th push drops the oldest.
const MAX_CONCURRENT = 3;

interface ToastAction {
  label: string;
  onClick: () => void;
}

interface ToastItem {
  id: string;
  title: string;
  variant: ToastVariant;
  action?: ToastAction;
  persistent?: boolean;
}

interface ToastContextValue {
  /**
   * `persistent` (§17.4): the update-available toast must stay up until the
   * user acts — auto-reloading mid-edit destroys unsaved input — so it opts
   * out of the variant's default auto-dismiss via Radix's per-`Toast.Root`
   * `duration` override rather than a new dismiss mechanism.
   */
  showToast: (
    title: string,
    variant?: ToastVariant,
    action?: ToastAction,
    persistent?: boolean,
  ) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }): ReactElement {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const showToast = useCallback(
    (title: string, variant: ToastVariant = 'info', action?: ToastAction, persistent?: boolean) => {
      const id = crypto.randomUUID();
      // §20.1: maximum three concurrent — the oldest collapses (is dropped)
      // once a fourth arrives.
      setToasts((current) => [
        ...current.slice(-(MAX_CONCURRENT - 1)),
        { id, title, variant, action, persistent },
      ]);
    },
    [],
  );

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      <Toast.Provider swipeDirection="right" duration={5000}>
        {children}
        {toasts.map((toast) => {
          const Icon = VARIANT_ICON[toast.variant];
          return (
            <Toast.Root
              key={toast.id}
              // §20.1: "assertive" for errors, "polite" for success/info —
              // Radix announces `type="foreground"` toasts immediately
              // (assertive) and `type="background"` ones politely.
              type={toast.variant === 'error' ? 'foreground' : 'background'}
              duration={toast.persistent ? Infinity : VARIANT_DURATIONS[toast.variant]}
              onOpenChange={(open) => {
                if (!open) {
                  dismiss(toast.id);
                }
              }}
              className={cn(
                'border-border bg-surface-raised shadow-overlay flex items-center gap-2 rounded-md border py-1 pr-1 pl-3',
                'data-[state=open]:animate-in data-[state=closed]:animate-out motion-reduce:transition-none',
                VARIANT_CLASS[toast.variant],
              )}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              <div className="min-w-0 flex-1 py-2">
                <Toast.Title className="text-text text-sm">{toast.title}</Toast.Title>
                {toast.action && (
                  <Toast.Action
                    altText={toast.action.label}
                    onClick={toast.action.onClick}
                    className="text-accent focus-visible:outline-accent mt-1 block text-sm font-medium underline focus-visible:outline focus-visible:outline-2"
                  >
                    {toast.action.label}
                  </Toast.Action>
                )}
              </div>
              {/* §21 A4: a 44×44 target, reserved as a flex sibling rather
                  than absolutely positioned, so it can't overlap the
                  adjacent toast in a 3-deep stack. */}
              <Toast.Close
                aria-label="Dismiss"
                className="text-text-muted focus-visible:outline-accent flex h-11 w-11 shrink-0 items-center justify-center rounded-sm focus-visible:outline focus-visible:outline-2"
              >
                ×
              </Toast.Close>
            </Toast.Root>
          );
        })}
        {/* §20.1: bottom-centre on mobile (above BottomNav's z-40 fixed bar,
            whose own height + safe-area is accounted for below), bottom-right
            on desktop where there's no bottom nav to clear. */}
        <Toast.Viewport className="fixed inset-x-4 bottom-[calc(4.5rem+env(safe-area-inset-bottom))] z-50 mx-auto flex w-auto max-w-80 flex-col gap-2 outline-none md:inset-x-auto md:right-4 md:bottom-4 md:mx-0" />
      </Toast.Provider>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
