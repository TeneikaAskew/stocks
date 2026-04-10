export function sessionLabel(session: string | undefined): string {
  const map: Record<string, string> = {
    regular: 'Market Open',
    'pre-market': 'Pre-Market',
    'after-hours': 'After Hours',
    closed: 'Market Closed',
  };
  return session ? (map[session] ?? session) : 'Market Closed';
}

export function sessionColor(session: string | undefined): string {
  if (session === 'regular') return 'bg-green-500';
  if (session === 'pre-market' || session === 'after-hours') return 'bg-amber-500';
  return 'bg-red-500';
}

export function sessionPillClasses(session: string | undefined): { pill: string; dot: string } {
  if (session === 'regular') {
    return { pill: 'bg-green-500/10 text-green-400', dot: 'bg-green-400' };
  }
  if (session === 'pre-market' || session === 'after-hours') {
    return { pill: 'bg-amber-500/10 text-amber-400', dot: 'bg-amber-400' };
  }
  return { pill: 'bg-red-500/10 text-red-400', dot: 'bg-red-400' };
}
