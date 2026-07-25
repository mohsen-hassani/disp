import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

// Standard clsx + tailwind-merge combo: clsx for conditional class logic,
// twMerge to resolve conflicting Tailwind utility classes (e.g. a default
// `p-4` overridden by a caller's `p-2`) by keeping the last one wins.
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
