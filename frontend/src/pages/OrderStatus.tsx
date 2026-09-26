import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, CalendarClock, CheckCircle2, ChefHat, Coffee, ListOrdered, Receipt } from 'lucide-react';
import { api } from '@/lib/api';
import { useSession } from '@/context/SessionContext';
import { clock, dayClock, minutes, rupees, STATUS_LABEL } from '@/lib/format';
import { useDoc, useNow } from '@/lib/hooks';
import type { Order } from '@/lib/types';
import { ErrorNote, PageLoader, StatusPill } from '@/components/ui';

const STEPS = [
  { key: 'placed', label: 'Queued', icon: ListOrdered },
  { key: 'in_progress', label: 'Being made', icon: ChefHat },
  { key: 'ready', label: 'Ready', icon: Coffee },
];

/** Live tracker: a Firestore listener on the order doc, so ETA changes appear instantly. */
export default function OrderStatus() {
  const { id } = useParams();
  const { data: live, error } = useDoc<Order>(id ? `orders/${id}` : null);
  // If the realtime listener can't connect (network, blocked websockets), poll the API.
  const [polled, setPolled] = useState<Order | null>(null);
  useEffect(() => {
    if (!error || !id) return;
    const load = () => api.get<Order>(`/orders/${id}`).then(setPolled).catch(() => undefined);
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [error, id]);
  const order = live ?? polled;
  const { replace } = useSession();
  const now = useNow(1000);
  const [err, setErr] = useState<string | null>(null);

  if (!order) return <PageLoader />;

  const step = order.status === 'collected' ? 3 : STEPS.findIndex((s) => s.key === order.status);
  const readyAt = order.eta ? new Date(order.eta.readyAt).getTime() : null;
  const remaining = readyAt ? Math.max(0, readyAt - now) : null;

  async function cancel() {
    setErr(null);
    try {
      await api.post(`/orders/${order!.id}/cancel`);
    } catch (e) {
      setErr((e as Error).message);
    }
  }
  async function reorder() {
    const s = await api.post<Parameters<typeof replace>[0]>(`/orders/${order!.id}/reorder`);
    replace(s);
  }

  return (
    <div className="space-y-4">
      <Link to="/orders" className="inline-flex items-center gap-1 text-sm text-bean-500"><ArrowLeft className="h-4 w-4" /> Orders</Link>

      <div className="card overflow-hidden">
        <div className="bg-bean-900 px-5 py-6 text-center text-cream-50">
          <p className="text-xs tracking-widest text-bean-300 uppercase">Pickup code</p>
          <p className="font-display text-5xl tracking-widest">{order.pickupCode}</p>
          <p className="mt-2 text-sm text-bean-300">{STATUS_LABEL[order.status]}</p>
        </div>

        <div className="p-5">
          {order.status === 'scheduled' && order.scheduledFor && (
            <div className="rise text-center">
              <CalendarClock className="mx-auto h-8 w-8 text-honey-500" />
              <p className="mt-2 font-display text-2xl">Ready {dayClock(order.scheduledFor)}</p>
              <p className="mt-1 text-sm text-bean-500">
                We'll start it{order.eta?.releaseAt ? ` around ${clock(order.eta.releaseAt)}` : ''} so it's fresh when you arrive.
              </p>
            </div>
          )}

          {['placed', 'in_progress'].includes(order.status) && order.eta && (
            <div className="rise text-center">
              <p className="text-sm text-bean-500">Ready in about</p>
              <p className="font-display text-5xl">{remaining !== null && remaining > 30000 ? minutes(remaining / 1000) : 'a moment'}</p>
              <p className="mt-1 text-sm text-bean-500">
                around {clock(order.eta.readyAt)} <span className="text-bean-300">({clock(order.eta.lowAt)}–{clock(order.eta.highAt)})</span>
              </p>
              {order.eta.queuePosition && order.eta.queuePosition > 1 && (
                <p className="mt-2 text-xs text-bean-500">{order.eta.queuePosition - 1} order{order.eta.queuePosition > 2 ? 's' : ''} ahead of you · updates live</p>
              )}
            </div>
          )}

          {order.status === 'ready' && (
            <div className="rise text-center">
              <CheckCircle2 className="mx-auto h-10 w-10 text-leaf-600" />
              <p className="mt-2 font-display text-2xl">It's ready!</p>
              <p className="text-sm text-bean-500">Show code <b>{order.pickupCode}</b> at the counter.</p>
            </div>
          )}

          {order.status !== 'cancelled' && order.status !== 'scheduled' && (
            <div className="mt-6 flex items-center justify-between">
              {STEPS.map((s, i) => {
                const Icon = s.icon;
                const done = i <= step;
                return (
                  <div key={s.key} className="flex flex-1 flex-col items-center gap-1">
                    <div className={`grid h-9 w-9 place-items-center rounded-full ${done ? 'bg-ember-600 text-white' : 'bg-cream-200 text-bean-300'}`}><Icon className="h-4 w-4" /></div>
                    <span className={`text-[11px] ${done ? 'font-semibold text-bean-900' : 'text-bean-300'}`}>{s.label}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="card p-4">
        <div className="mb-2 flex items-center justify-between">
          <p className="flex items-center gap-1.5 font-medium"><Receipt className="h-4 w-4" /> Receipt</p>
          <StatusPill status={order.status} />
        </div>
        <ul className="space-y-1.5 text-sm">
          {order.items.map((l) => (
            <li key={l.lineId} className="flex justify-between gap-2">
              <span>{l.qty}× {l.name}{l.modifierLabels.length ? <span className="text-bean-500"> · {l.modifierLabels.join(', ')}</span> : null}</span>
              <span>{rupees(l.lineTotal)}</span>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex justify-between border-t border-cream-200 pt-3 font-semibold">
          <span>Total</span><span>{rupees(order.total)}</span>
        </div>
        <p className="mt-2 text-xs text-bean-500">
          {order.payment.status === 'paid' ? `Paid by ${order.payment.method.toUpperCase()} (demo) · ${order.payment.txnId}` : order.payment.status === 'refunded' ? 'Refunded (demo)' : 'Pay at the counter'}
        </p>
      </div>

      <ErrorNote>{err}</ErrorNote>
      <div className="flex gap-2">
        {['placed', 'scheduled'].includes(order.status) && <button className="btn-ghost flex-1 text-berry-600" onClick={cancel}>Cancel order</button>}
        {['collected', 'cancelled', 'ready'].includes(order.status) && <button className="btn-primary flex-1" onClick={reorder}>Order again</button>}
      </div>
    </div>
  );
}
