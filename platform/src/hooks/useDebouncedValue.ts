import { useEffect, useState } from 'react';

/**
 * Pure scheduling primitive behind `useDebouncedValue`, extracted so it can
 * be unit-tested without rendering a React tree (this repo's frontend test
 * style avoids @testing-library/react — see MovementRead.test.tsx). Schedules
 * `onSettle(value)` to fire after `ms` of inactivity; returns a cancel
 * function that clears the pending timer.
 */
export function scheduleDebounce<T>(value: T, ms: number, onSettle: (v: T) => void): () => void {
  const t = setTimeout(() => onSettle(value), ms);
  return () => clearTimeout(t);
}

/** Returns `value` after it has been stable for `ms` — for network-backed type-aheads. */
export function useDebouncedValue<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    return scheduleDebounce(value, ms, setDebounced);
  }, [value, ms]);
  return debounced;
}
