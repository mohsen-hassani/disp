import { useRegisterSW } from 'virtual:pwa-register/react';

export interface ServiceWorkerUpdate {
  needRefresh: boolean;
  updateServiceWorker: (reloadPage?: boolean) => Promise<void>;
}

/**
 * §17.4: `registerType: 'prompt'` (vite.config.ts) means the generated
 * service worker never activates a waiting update on its own — this hook is
 * what registers it and surfaces `needRefresh` when one is waiting, for
 * `UpdatePrompt.tsx` to turn into a toast. Registration errors are logged,
 * not surfaced to the user — a failed *registration* doesn't break the app,
 * it just means this session runs without offline support until the next
 * successful load.
 */
export function useServiceWorkerUpdate(): ServiceWorkerUpdate {
  const {
    needRefresh: [needRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisterError(error) {
      console.error('Service worker registration failed', error);
    },
  });

  return { needRefresh, updateServiceWorker };
}
