/** Convert "HH:MM:SS" (24h) to "H:MM:SS AM/PM" (12h). */
export function to12h(hms: string | null | undefined): string {
  if (!hms) return '';
  const parts = hms.split(':');
  if (parts.length < 2) return hms;
  const h = Number(parts[0]);
  const m = parts[1];
  const s = parts[2];
  if (Number.isNaN(h)) return hms;
  const period = h >= 12 ? 'PM' : 'AM';
  const h12 = ((h + 11) % 12) + 1;
  return s ? `${h12}:${m}:${s} ${period}` : `${h12}:${m} ${period}`;
}
