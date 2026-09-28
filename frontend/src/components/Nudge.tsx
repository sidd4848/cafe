import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Timer, X } from 'lucide-react';
import { api } from '@/lib/api';
import { useSession } from '@/context/SessionContext';
import { clock, minutes } from '@/lib/format';

export interface Nudge {
  id: string;
  fromAt: string;
  toAt: string;
  fromWaitSec: number | null;
  toWaitSec: number | null;
  beans: number;
  status: string;
}

const KEY = 'cc.nudge';

/** The accepted offer travels to checkout, which redeems it for the bonus beans. */
export function acceptedNudge(): Nudge | null {
  try {
    const n = JSON.parse(sessionStorage.getItem(KEY) ?? 'null') as Nudge | null;
    return n && new Date(n.toAt).getTime() > Date.now() - 15 * 60000 ? n : null;
  } catch {
    return null;
  }
}
export function clearAcceptedNudge() {
  try { sessionStorage.removeItem(KEY); } catch { /* storage blocked */ }
}

export function useNudge(context: 'home' | 'checkout', enabled = true) {
  const { cafeId } = useSession();
  const [nudge, setNudge] = useState<Nudge | null>(null);
  useEffect(() => {
    if (!enabled) return;
    api.get<Nudge | null>(`/cafes/${cafeId}/nudge?context=${context}`).then(setNudge).catch(() => setNudge(null));
  }, [cafeId, context, enabled]);
  return [nudge, setNudge] as const;
}

export async function acceptNudge(n: Nudge, setPickup: (iso: string | null) => Promise<void>) {
  await api.post(`/nudges/${n.id}/respond`, { accept: true });
  try { sessionStorage.setItem(KEY, JSON.stringify(n)); } catch { /* storage blocked */ }
  await setPickup(n.toAt);
}

/** Home screen: "beat the rush" offer for guests who usually come in a peak. */
export function NudgeCard() {
  const [nudge, setNudge] = useNudge('home');
  const { session, setPickup, setCheckoutOpen } = useSession();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  if (!nudge || nudge.status !== 'offered') return null;

  async function accept() {
    setBusy(true);
    try {
      await acceptNudge(nudge!, setPickup);
      setNudge({ ...nudge!, status: 'accepted' });
      if (session?.cart.length) setCheckoutOpen(true);
      else nav('/order');
    } finally {
      setBusy(false);
    }
  }
  async function decline() {
    await api.post(`/nudges/${nudge!.id}/respond`, { accept: false }).catch(() => undefined);
    setNudge(null);
  }

  return (
    <section className="card rise relative overflow-hidden border-honey-500/50 bg-gradient-to-br from-honey-100 to-cream-50 p-4">
      <button onClick={decline} className="absolute top-3 right-3 text-bean-500" aria-label="No thanks"><X className="h-4 w-4" /></button>
      <p className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-bean-700 uppercase"><Timer className="h-3.5 w-3.5" /> Beat the rush</p>
      <p className="mt-1 font-display text-xl leading-snug">
        Around {clock(nudge.fromAt)} the bar gets busy{nudge.fromWaitSec ? ` (~${minutes(nudge.fromWaitSec)} wait)` : ''}.
        Pick up at <b>{clock(nudge.toAt)}</b> instead?
      </p>
      <p className="mt-1 text-sm text-bean-700">It'll be fresh and waiting, and you get <b>+{nudge.beans} beans</b>.</p>
      <button className="btn-primary mt-3 w-full" disabled={busy} onClick={accept}>
        <Sparkles className="h-4 w-4" /> Pre-order for {clock(nudge.toAt)} · +{nudge.beans} beans
      </button>
    </section>
  );
}
