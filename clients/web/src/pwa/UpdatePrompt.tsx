import { useEffect, useRef } from 'react';

import { useToast } from '../components/feedback/ToastProvider';
import { useServiceWorkerUpdate } from './registerSW';

/**
 * §17.4: a non-blocking, persistent toast — never an auto-reload, which
 * would destroy unsaved input (a note mid-edit, a dirty settings form).
 * Renders nothing itself; mounted once in main.tsx, outside the auth guard,
 * since an update can be waiting whether or not the user is signed in.
 */
export function UpdatePrompt(): null {
  const { needRefresh, updateServiceWorker } = useServiceWorkerUpdate();
  const { showToast } = useToast();
  const shownRef = useRef(false);

  useEffect(() => {
    if (needRefresh && !shownRef.current) {
      shownRef.current = true;
      showToast(
        'A new version is available.',
        'default',
        { label: 'Reload', onClick: () => void updateServiceWorker(true) },
        true,
      );
    }
  }, [needRefresh, showToast, updateServiceWorker]);

  return null;
}
