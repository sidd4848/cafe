import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CalendarClock, CreditCard, Minus, Plus, ShoppingBag, Smartphone, Store, Trash2, Utensils, Zap } from 'lucide-react';
import { useSession } from '@/context/SessionContext';
import { api } from '@/lib/api';
import { dayClock, minutes, rupees, toLocalInput } from '@/lib/format';
import { useLiveStats } from '@/lib/hooks';
import type { Order } from '@/lib/types';
import { ErrorNote, Sheet, Spinner } from './ui';

/** Sticky bar above the tab bar whenever the cart has something in it. */
export function CartBar() {
  const { session, setCheckoutOpen } = useSession();
  const count = session?.cart.reduce((n, l) => n + l.qty, 0) ?? 0;
  if (!count) return null;
  return (
    <button onClick={() => setCheckoutOpen(true)} className="rise fixed inset-x-0 bottom-[68px] z-30 mx-auto flex max-w-md items-center justify-between rounded-2xl bg-bean-900 px-5 py-3.5 text-cream-50 shadow-lg" style={{ width: 'calc(100% - 2rem)' }}>
      <span className="flex items-center gap-2 text-sm font-medium">
        <ShoppingBag className="h-4 w-4" /> {count} item{count > 1 ? 's' : ''}
        {session?.pickupAt && <span className="rounded-full bg-honey-500 px-2 py-0.5 text-[11px] font-bold text-bean-950">Pre-order</span>}
      </span>
      <span className="font-semibold">Checkout · {rupees(session!.total)}</span>
    </button>
  );
}

type PayMethod = 'upi' | 'card' | 'counter';

interface TableCtx { cafe: string; table: string; token: string; label: string }
function readTable(): TableCtx | null {
  try {
    const raw = sessionStorage.getItem('cc.table');
    return raw ? (JSON.parse(raw) as TableCtx) : null;
  } catch {
    return null;
  }
}

export function CheckoutSheet() {
  const { session, cartOp, setPickup, checkoutOpen, setCheckoutOpen, cafeId, reload } = useSession();
  const live = useLiveStats();
  const nav = useNavigate();
  const [when, setWhen] = useState<'asap' | 'later'>('asap');
  const [pickup, setPickupLocal] = useState('');
  const [method, setMethod] = useState<PayMethod>('upi');
  const [stage, setStage] = useState<'review' | 'paying'>('review');
  const [error, setError] = useState<string | null>(null);
  const [table, setTable] = useState<TableCtx | null>(null);
  const [dineIn, setDineIn] = useState(false);

  useEffect(() => {
    if (!checkoutOpen) return;
    const t = readTable();
    setTable(t);
    setDineIn(!!t);
    setStage('review');
    setError(null);
    if (session?.pickupAt) {
      setWhen('later');
      setPickupLocal(toLocalInput(new Date(session.pickupAt)));
    } else {
      setWhen('asap');
      setPickupLocal(toLocalInput(new Date(Date.now() + 30 * 60000)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkoutOpen]);

  if (!session) return null;
  const close = () => setCheckoutOpen(false);

  async function pay() {
    setError(null);
    const pickupAt = !dineIn && when === 'later' && pickup ? new Date(pickup).toISOString() : null;
    if (!dineIn && when === 'later' && (!pickupAt || new Date(pickupAt).getTime() < Date.now())) {
      setError('Pick a time in the future.');
      return;
    }
    setStage('paying');
    try {
      await setPickup(pickupAt);
      // Simulated gateway: a short pause so the flow feels like a real payment.
      if (method !== 'counter') await new Promise((r) => setTimeout(r, 1200));
      const order = await api.post<Order>(`/cafes/${cafeId}/checkout`, {
        paymentMethod: method,
        pickupAt,
        ...(dineIn && table ? { tableId: table.table, tableToken: table.token } : {}),
      });
      await reload();
      close();
      nav(`/orders/${order.id}`);
    } catch (e) {
      setError((e as Error).message);
      setStage('review');
    }
  }

  const methods: { id: PayMethod; label: string; icon: typeof Smartphone }[] = [
    { id: 'upi', label: 'UPI', icon: Smartphone },
    { id: 'card', label: 'Card', icon: CreditCard },
    { id: 'counter', label: dineIn ? 'Pay at table later' : 'Pay at counter', icon: Store },
  ];

  return (
    <Sheet open={checkoutOpen} onClose={close} title="Your order">
      {stage === 'paying' ? (
        <div className="flex flex-col items-center gap-3 py-10 text-center">
          <Spinner className="h-8 w-8" />
          <p className="font-display text-lg">{method === 'counter' ? 'Placing your order…' : 'Processing demo payment…'}</p>
          <p className="text-xs text-bean-500">No real money moves. This is a simulated payment.</p>
        </div>
      ) : (
        <>
          <ul className="divide-y divide-cream-200">
            {session.cart.map((l) => (
              <li key={l.lineId} className="flex items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{l.name}</p>
                  {l.modifierLabels.length > 0 && <p className="truncate text-xs text-bean-500">{l.modifierLabels.join(' · ')}</p>}
                </div>
                <div className="flex items-center rounded-lg border border-cream-300 bg-white">
                  <button className="p-1.5" onClick={() => (l.qty > 1 ? cartOp({ op: 'update', lineId: l.lineId, qty: l.qty - 1 }) : cartOp({ op: 'remove', lineId: l.lineId }))} aria-label="Less">
                    {l.qty > 1 ? <Minus className="h-3.5 w-3.5" /> : <Trash2 className="h-3.5 w-3.5 text-berry-600" />}
                  </button>
                  <span className="w-5 text-center text-sm font-semibold">{l.qty}</span>
                  <button className="p-1.5" onClick={() => cartOp({ op: 'update', lineId: l.lineId, qty: l.qty + 1 })} aria-label="More"><Plus className="h-3.5 w-3.5" /></button>
                </div>
                <span className="w-14 text-right text-sm font-semibold">{rupees(l.lineTotal)}</span>
              </li>
            ))}
          </ul>
          {session.cart.length === 0 && <p className="py-6 text-center text-sm text-bean-500">Your cart is empty.</p>}

          {table && (
            <div className="mt-5 grid grid-cols-2 gap-2">
              <button onClick={() => setDineIn(true)} className={`card flex items-center gap-2 px-3 py-3 text-sm ${dineIn ? 'border-bean-900 ring-1 ring-bean-900' : ''}`}><Utensils className="h-4 w-4 text-ember-600" /> To {table.label}</button>
              <button onClick={() => setDineIn(false)} className={`card flex items-center gap-2 px-3 py-3 text-sm ${!dineIn ? 'border-bean-900 ring-1 ring-bean-900' : ''}`}><ShoppingBag className="h-4 w-4 text-ember-600" /> Takeaway</button>
            </div>
          )}
          {!dineIn && <>
          <p className="label mt-5">When</p>
          <div className="grid grid-cols-2 gap-2">
            <button onClick={() => setWhen('asap')} className={`card flex items-center gap-2 px-3 py-3 text-left text-sm ${when === 'asap' ? 'border-bean-900 ring-1 ring-bean-900' : ''}`}>
              <Zap className="h-4 w-4 text-ember-600" />
              <span>ASAP{live ? <span className="block text-xs text-bean-500">~{minutes(live.currentWaitSec)}</span> : null}</span>
            </button>
            <button onClick={() => setWhen('later')} className={`card flex items-center gap-2 px-3 py-3 text-left text-sm ${when === 'later' ? 'border-bean-900 ring-1 ring-bean-900' : ''}`}>
              <CalendarClock className="h-4 w-4 text-ember-600" />
              <span>Pre-order<span className="block text-xs text-bean-500">pick a time</span></span>
            </button>
          </div>
          {when === 'later' && (
            <div className="mt-3">
              <input type="datetime-local" className="w-full" value={pickup} min={toLocalInput(new Date())} onChange={(e) => setPickupLocal(e.target.value)} />
              {pickup && <p className="mt-1.5 text-xs text-bean-500">We'll start it so it's fresh at {dayClock(new Date(pickup))}.</p>}
            </div>
          )}
          </>}

          <p className="label mt-5">Payment <span className="normal-case tracking-normal text-bean-300">(simulated)</span></p>
          <div className="grid grid-cols-3 gap-2">
            {methods.map(({ id, label, icon: Icon }) => (
              <button key={id} onClick={() => setMethod(id)} className={`card flex flex-col items-center gap-1 px-2 py-3 text-xs font-medium ${method === id ? 'border-bean-900 ring-1 ring-bean-900' : ''}`}>
                <Icon className="h-4 w-4" /> {label}
              </button>
            ))}
          </div>

          <div className="mt-5"><ErrorNote>{error}</ErrorNote></div>
          <button className="btn-accent mt-3 w-full py-3" disabled={!session.cart.length} onClick={pay}>
            {method === 'counter' ? 'Place order' : 'Pay'} · {rupees(session.total)}
          </button>
          <p className="mt-2 text-center text-[11px] text-bean-500">Demo checkout. No card or UPI details are collected.</p>
        </>
      )}
    </Sheet>
  );
}
