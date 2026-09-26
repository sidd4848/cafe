import { useEffect, useMemo, useState } from 'react';
import { collection, query, where } from 'firebase/firestore';
import { CalendarClock, ChefHat, Coffee, ListOrdered, Minus, Plus, Utensils, X } from 'lucide-react';
import { api } from '@/lib/api';
import { firestore } from '@/lib/firebase';
import { config } from '@/lib/config';
import { clock, dayClock, minutes, rupees } from '@/lib/format';
import { useLiveStats, useNow, useQuery } from '@/lib/hooks';
import type { Order, OrderStatus } from '@/lib/types';
import { ErrorNote } from '@/components/ui';

const COLUMNS: { status: OrderStatus; title: string; icon: typeof Coffee; next?: OrderStatus; action?: string }[] = [
  { status: 'placed', title: 'Queued', icon: ListOrdered, next: 'in_progress', action: 'Start' },
  { status: 'in_progress', title: 'Making', icon: ChefHat, next: 'ready', action: 'Ready' },
  { status: 'ready', title: 'Ready for pickup', icon: Coffee, next: 'collected', action: 'Handed over' },
];

interface Today { orders: number; cancelled: number; revenue: number; preorders: number; medianWaitSec: number | null; etaAbsErrorEwmaSec: number | null }

/** Barista board, kept live by a Firestore listener; the API does every state change. */
export default function Board() {
  const cafeId = config.cafeId;
  const q = useMemo(() => query(collection(firestore, 'orders'), where('cafeId', '==', cafeId), where('status', 'in', ['scheduled', 'placed', 'in_progress', 'ready'])), [cafeId]);
  const { data: orders, error } = useQuery<Order>(q, `board-${cafeId}`);
  const live = useLiveStats(cafeId);
  const now = useNow(5000);
  const [today, setToday] = useState<Today | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.get<Today>(`/staff/cafes/${cafeId}/today`).then(setToday).catch(() => undefined);
  }, [cafeId, orders.length]);

  const move = async (id: string, status: OrderStatus) => {
    setErr(null);
    try {
      await api.post(`/staff/orders/${id}/status`, { status });
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const setBaristas = (n: number) => api.patch(`/staff/cafes/${cafeId}`, { baristasOnShift: n }).catch((e) => setErr(e.message));

  const byStatus = (s: OrderStatus) =>
    orders.filter((o) => o.status === s).sort((a, b) => (a.placedAt ?? a.createdAt).localeCompare(b.placedAt ?? b.createdAt));
  const scheduled = orders.filter((o) => o.status === 'scheduled').sort((a, b) => (a.scheduledFor ?? '').localeCompare(b.scheduledFor ?? ''));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-3xl">Orders</h1>
        {[
          ['Wait now', live ? minutes(live.currentWaitSec) : '–'],
          ['Today', today ? `${today.orders} orders · ${rupees(today.revenue)}` : '–'],
          ['Median wait', today?.medianWaitSec ? minutes(today.medianWaitSec) : '–'],
          ['ETA accuracy', live?.etaAbsErrorEwmaSec != null ? `±${minutes(live.etaAbsErrorEwmaSec)}` : '–'],
        ].map(([k, v]) => (
          <div key={k} className="card px-3 py-2"><p className="text-[11px] text-bean-500 uppercase">{k}</p><p className="font-semibold">{v}</p></div>
        ))}
        <div className="card flex items-center gap-2 px-3 py-2">
          <div><p className="text-[11px] text-bean-500 uppercase">Baristas</p><p className="font-semibold">{live?.baristasOnShift ?? '–'}</p></div>
          <button className="rounded-md border border-cream-300 p-1" onClick={() => live && setBaristas(Math.max(1, live.baristasOnShift - 1))} aria-label="Fewer baristas"><Minus className="h-3.5 w-3.5" /></button>
          <button className="rounded-md border border-cream-300 p-1" onClick={() => live && setBaristas(live.baristasOnShift + 1)} aria-label="More baristas"><Plus className="h-3.5 w-3.5" /></button>
        </div>
      </div>
      <ErrorNote>{error || err}</ErrorNote>

      <div className="grid gap-4 lg:grid-cols-4">
        {COLUMNS.map(({ status, title, icon: Icon, next, action }) => {
          const list = byStatus(status);
          return (
            <section key={status} className="rounded-2xl bg-cream-200/60 p-3">
              <h2 className="mb-3 flex items-center gap-2 font-sans text-sm font-semibold"><Icon className="h-4 w-4" /> {title} <span className="ml-auto rounded-full bg-cream-50 px-2 text-xs">{list.length}</span></h2>
              <div className="space-y-2.5">
                {list.map((o) => {
                  const age = Math.round((now - new Date(o.startedAt ?? o.placedAt ?? o.createdAt).getTime()) / 60000);
                  const late = o.eta && status !== 'ready' && now > new Date(o.eta.highAt).getTime();
                  return (
                    <div key={o.id} className={`card rise p-3 ${late ? 'border-berry-600/60' : ''}`}>
                      <div className="flex items-center gap-2">
                        <span className="rounded-lg bg-bean-900 px-2 py-0.5 font-display text-lg tracking-wider text-cream-50">{o.pickupCode}</span>
                        <span className="text-sm font-medium">{o.customerName}</span>
                        {o.dineIn && <span className="flex items-center gap-0.5 rounded bg-honey-100 px-1.5 text-[10px] font-bold"><Utensils className="h-3 w-3" />{o.tableLabel}</span>}
                        <span className={`ml-auto text-xs ${late ? 'font-semibold text-berry-600' : 'text-bean-500'}`}>{age}m</span>
                      </div>
                      <ul className="mt-2 space-y-0.5 text-sm">
                        {o.items.map((l) => (
                          <li key={l.lineId}><b>{l.qty}×</b> {l.name}{l.modifierLabels.length > 0 && <span className="text-bean-500"> · {l.modifierLabels.join(', ')}</span>}</li>
                        ))}
                      </ul>
                      {o.notes && <p className="mt-1 text-xs text-ember-600">Note: {o.notes}</p>}
                      <div className="mt-2 flex items-center gap-2 text-xs text-bean-500">
                        {o.eta && status !== 'ready' && <span>ETA {clock(o.eta.readyAt)}</span>}
                        {o.payment.status === 'pending' && <span className="rounded bg-honey-100 px-1.5 font-semibold text-bean-800">Unpaid {rupees(o.total)}</span>}
                      </div>
                      <div className="mt-2.5 flex gap-2">
                        {next && <button className="btn-primary flex-1 py-1.5" onClick={() => move(o.id, next)}>{action}</button>}
                        {status !== 'ready' && <button className="btn-ghost px-2 py-1.5" onClick={() => confirm('Cancel this order?') && move(o.id, 'cancelled')} aria-label="Cancel"><X className="h-4 w-4" /></button>}
                      </div>
                    </div>
                  );
                })}
                {list.length === 0 && <p className="py-6 text-center text-xs text-bean-500">Nothing here</p>}
              </div>
            </section>
          );
        })}
        <section className="rounded-2xl border border-dashed border-cream-300 p-3">
          <h2 className="mb-3 flex items-center gap-2 font-sans text-sm font-semibold"><CalendarClock className="h-4 w-4" /> Pre-orders <span className="ml-auto rounded-full bg-cream-200 px-2 text-xs">{scheduled.length}</span></h2>
          <div className="space-y-2">
            {scheduled.map((o) => (
              <div key={o.id} className="card p-3 text-sm">
                <div className="flex items-center justify-between"><b>{o.pickupCode} · {o.customerName}</b><span className="text-xs">{o.scheduledFor && dayClock(o.scheduledFor)}</span></div>
                <p className="mt-1 text-xs text-bean-500">{o.items.map((l) => `${l.qty}× ${l.name}`).join(', ')}</p>
                {o.eta?.releaseAt && <p className="mt-1 text-[11px] text-bean-500">Auto-joins queue ~{clock(o.eta.releaseAt)}</p>}
              </div>
            ))}
            {scheduled.length === 0 && <p className="py-6 text-center text-xs text-bean-500">No pre-orders</p>}
          </div>
        </section>
      </div>
    </div>
  );
}
