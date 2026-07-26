import { useNavigate } from '@tanstack/react-router';
import { useEffect, useRef } from 'react';

const CHORD_TIMEOUT_MS = 800;

interface UseKeyboardShortcutsParams {
  onOpenCreateNote: () => void;
  onOpenShortcuts: () => void;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;
}

/**
 * §16.5, global and app-wide (not scoped to `/notes`) since `n` must open
 * the note-creation dialog from any screen. "Active only when no input has
 * focus" is the spec's own guard against hijacking normal typing. `/`'s
 * search-focus only does anything on `/notes` (the only screen with
 * `#notes-search`), so it's a silent no-op elsewhere rather than needing a
 * route check here.
 */
export function useKeyboardShortcuts({
  onOpenCreateNote,
  onOpenShortcuts,
}: UseKeyboardShortcutsParams): void {
  const navigate = useNavigate();
  const pendingGRef = useRef(false);
  const chordTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent): void {
      if (isTypingTarget(event.target) || event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }

      if (pendingGRef.current) {
        pendingGRef.current = false;
        clearTimeout(chordTimerRef.current);
        if (event.key === 'd') {
          event.preventDefault();
          void navigate({ to: '/' });
        } else if (event.key === 'n') {
          event.preventDefault();
          void navigate({ to: '/notes' });
        }
        return;
      }

      switch (event.key) {
        case 'g':
          pendingGRef.current = true;
          chordTimerRef.current = setTimeout(() => {
            pendingGRef.current = false;
          }, CHORD_TIMEOUT_MS);
          break;
        case 'n':
          event.preventDefault();
          onOpenCreateNote();
          break;
        case '/': {
          const searchInput = document.getElementById('notes-search');
          if (searchInput instanceof HTMLInputElement) {
            event.preventDefault();
            searchInput.focus();
          }
          break;
        }
        case '?':
          event.preventDefault();
          onOpenShortcuts();
          break;
        default:
          break;
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      clearTimeout(chordTimerRef.current);
    };
  }, [navigate, onOpenCreateNote, onOpenShortcuts]);
}
