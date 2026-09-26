import { Clock } from 'lucide-react';
import { useLiveStats } from '@/lib/hooks';
import { minutes } from '@/lib/format';

/** Live wait at the counter, straight from the `stats/live` doc the ETA engine writes. */
export function WaitBadge({ compact = false }: { compact?: boolean }) {
  const live = useLiveStats();
  if (!live) return null;
  const w = live.currentWaitSec;
  const tone = w < 240 ? 'bg-leaf-100 text-leaf-600' : w < 420 ? 'bg-honey-100 text-bean-800' : 'bg-berry-100 text-berry-600';
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${tone}`}>
      <span className="relative flex h-1.5 w-1.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-60" />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
      </span>
      {compact ? <Clock className="h-3 w-3" /> : null}
      ~{minutes(w)} wait{compact ? '' : ` · ${live.activeOrders} in queue`}
    </span>
  );
}
