import { useEffect, useState } from 'react';

/**
 * Progressive line-reveal for the hero agent terminal.
 * Returns how many lines are visible. Reveals one line per `intervalMs`.
 * Honors prefers-reduced-motion by revealing everything immediately.
 */
export function useTypingLines(total: number, intervalMs = 650): number {
  const [visible, setVisible] = useState(0);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setVisible(total);
      return;
    }
    setVisible(0);
    const id = window.setInterval(() => {
      setVisible((v) => {
        if (v + 1 >= total) window.clearInterval(id);
        return Math.min(v + 1, total);
      });
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [total, intervalMs]);

  return visible;
}
