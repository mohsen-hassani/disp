import * as Toast from '@radix-ui/react-toast';
import {
  type ReactElement,
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useState,
} from 'react';

import { cn } from '../../lib/cn';

type ToastVariant = 'default' | 'danger';

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
   * out of the Provider's default 6s auto-dismiss via Radix's per-`Toast.Root`
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

/**
 * Formally M10's file. Pulled forward because §13.6/§7.3 need a toast
 * surface for tile-action errors before M10's dedicated feedback milestone
 * exists — same call as M04 made for M06's SchemaForm. M10 owns polishing
 * this further (e.g. §21's broader toast-stacking a11y requirements).
 */
export function ToastProvider({ children }: { children: ReactNode }): ReactElement {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const showToast = useCallback(
    (
      title: string,
      variant: ToastVariant = 'default',
      action?: ToastAction,
      persistent?: boolean,
    ) => {
      const id = crypto.randomUUID();
      setToasts((current) => [...current, { id, title, variant, action, persistent }]);
    },
    [],
  );

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      <Toast.Provider swipeDirection="right" duration={6000}>
        {children}
        {toasts.map((toast) => (
          <Toast.Root
            key={toast.id}
            duration={toast.persistent ? Infinity : undefined}
            onOpenChange={(open) => {
              if (!open) {
                dismiss(toast.id);
              }
            }}
            className={cn(
              'border-border bg-surface-raised shadow-overlay rounded-md border p-3 pr-8',
              'data-[state=open]:animate-in data-[state=closed]:animate-out',
              toast.variant === 'danger' && 'border-danger',
            )}
          >
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
            <Toast.Close
              aria-label="Dismiss"
              className="text-text-muted focus-visible:outline-accent absolute top-2 right-2 rounded-sm focus-visible:outline focus-visible:outline-2"
            >
              ×
            </Toast.Close>
          </Toast.Root>
        ))}
        <Toast.Viewport className="fixed right-4 bottom-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2 pb-[env(safe-area-inset-bottom)] outline-none" />
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
