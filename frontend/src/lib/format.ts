export const rupees = (paise: number) => `₹${Math.round(paise / 100).toLocaleString('en-IN')}`;

export function minutes(sec: number): string {
  const m = Math.max(1, Math.round(sec / 60));
  return `${m} min`;
}

export function clock(iso: string | Date): string {
  const d = typeof iso === 'string' ? new Date(iso) : iso;
  return d.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' });
}

export function dayClock(iso: string | Date): string {
  const d = typeof iso === 'string' ? new Date(iso) : iso;
  const today = new Date();
  const tomorrow = new Date(today.getTime() + 86400000);
  const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  const day = sameDay(d, today) ? 'Today' : sameDay(d, tomorrow) ? 'Tomorrow' : d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });
  return `${day}, ${clock(d)}`;
}

export function countdown(ms: number): string {
  if (ms <= 0) return '0m';
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  return h ? `${h}h ${m}m` : `${m}m`;
}

/** <input type="datetime-local"> value in the browser's local time. */
export function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export const STATUS_LABEL: Record<string, string> = {
  scheduled: 'Pre-ordered',
  placed: 'In the queue',
  in_progress: 'Being made',
  ready: 'Ready to collect',
  collected: 'Collected',
  cancelled: 'Cancelled',
};
