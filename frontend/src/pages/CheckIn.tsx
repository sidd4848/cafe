import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Coffee, CreditCard, Smartphone, Sparkles } from 'lucide-react';
import { api } from '@/lib/api';
import { rupees } from '@/lib/format';
import type { Order } from '@/lib/types';
import { ErrorNote, PageLoader, Spinner } from '@/components/ui';

interface Landing {
  table: { id: string; label: string; seats: number; zone: string; serverName?: string };
  openOrders: Order[];
  balance: number;
  cafe: { id: string; name: string };
}

export const TABLE_KEY = 'cc.table';

/**
 * Where a table's QR lands: /checkin?cafe=..&table=T5&t=<daily token>.
 * One scan gives three things: order to this table, pay the bill, and check in to Connect.
 */
export default function CheckIn() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const cafe = params.get('cafe') ?? '';
  const table = params.get('table');
  const token = params.get('t') ?? '';
  const [landing, setLanding] = useState<Landing | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const load = () => {
    if (!table) return;
    api.get<Landing>(`/cafes/${cafe}/tables/${table}?t=${encodeURIComponent(token)}`)
      .then((l) => {
        setLanding(l);
        // Remember the table so checkout sends the order here (for this browser session).
        try { sessionStorage.setItem(TABLE_KEY, JSON.stringify({ cafe, table, token, label: l.table.label })); } catch { /* storage blocked */ }
      })
      .catch((e) => setErr(e.message));
  };
  useEffect(load, [cafe, table, token]); // eslint-disable-line react-hooks/exhaustive-deps

  async function connect() {
    setBusy('connect');
    setErr(null);
    try {
      await api.post('/connect/checkin', { cafeId: cafe, token, tableId: table });
      nav('/connect');
    } catch (e) {
      const msg = (e as Error).message;
      if (msg.includes('profile')) nav('/connect');
      else setErr(msg);
    } finally {
      setBusy(null);
    }
  }

  async function pay(method: 'upi' | 'card') {
    setBusy(method);
    setErr(null);
    try {
      await new Promise((r) => setTimeout(r, 1200)); // simulated gateway
      const r = await api.post<{ total: number }>(`/cafes/${cafe}/tables/${table}/pay`, { t: token, method });
      setDone(`Paid ${rupees(r.total)} (demo). Thank you!`);
      load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (!table) {
    return <div className="mx-auto max-w-md p-6"><ErrorNote>This QR code is missing its table. Please scan again.</ErrorNote></div>;
  }
  if (err && !landing) return <div className="mx-auto max-w-md p-6"><ErrorNote>{err}</ErrorNote><Link to="/" className="btn-ghost mt-4 w-full">Go home</Link></div>;
  if (!landing) return <PageLoader />;

  return (
    <div className="mx-auto min-h-screen max-w-md px-5 py-8">
      <p className="text-sm text-bean-500">{landing.cafe.name}</p>
      <h1 className="text-4xl">{landing.table.label}</h1>
      <p className="text-sm text-bean-500">
        Seats {landing.table.seats}{landing.table.serverName ? ` · your server is ${landing.table.serverName}` : ''}
      </p>

      <div className="mt-6 grid gap-3">
        <Link to="/order" className="card flex items-center gap-3 p-4">
          <Coffee className="h-6 w-6 text-ember-600" />
          <div className="flex-1"><p className="font-medium">Order to this table</p><p className="text-xs text-bean-500">Chat or browse; we'll bring it over</p></div>
          <ArrowRight className="h-4 w-4 text-bean-500" />
        </Link>

        <div className="card p-4">
          <div className="flex items-center gap-3">
            <CreditCard className="h-6 w-6 text-ember-600" />
            <div className="flex-1"><p className="font-medium">Pay your bill</p><p className="text-xs text-bean-500">No need to flag anyone down</p></div>
            <span className="font-display text-xl">{rupees(landing.balance)}</span>
          </div>
          {landing.openOrders.length > 0 ? (
            <>
              <ul className="mt-3 space-y-1 text-sm text-bean-700">
                {landing.openOrders.flatMap((o) => o.items).map((l, i) => (
                  <li key={i} className="flex justify-between"><span>{l.qty}× {l.name}</span><span>{rupees(l.lineTotal)}</span></li>
                ))}
              </ul>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <button className="btn-accent" disabled={!!busy} onClick={() => pay('upi')}>{busy === 'upi' ? <Spinner className="h-4 w-4 text-white" /> : <Smartphone className="h-4 w-4" />} UPI</button>
                <button className="btn-primary" disabled={!!busy} onClick={() => pay('card')}>{busy === 'card' ? <Spinner className="h-4 w-4 text-white" /> : <CreditCard className="h-4 w-4" />} Card</button>
              </div>
              <p className="mt-2 text-center text-[11px] text-bean-500">Simulated payment. No card or UPI details are collected.</p>
            </>
          ) : (
            <p className="mt-2 flex items-center gap-1.5 text-sm text-leaf-600">{done ? <><CheckCircle2 className="h-4 w-4" /> {done}</> : 'Nothing to pay right now.'}</p>
          )}
        </div>

        <button onClick={connect} disabled={!!busy} className="card flex items-center gap-3 p-4 text-left">
          <Sparkles className="h-6 w-6 text-ember-600" />
          <div className="flex-1"><p className="font-medium">Check in to Connect</p><p className="text-xs text-bean-500">See who's here and open to a chat</p></div>
          {busy === 'connect' ? <Spinner className="h-4 w-4" /> : <ArrowRight className="h-4 w-4 text-bean-500" />}
        </button>
      </div>
      <div className="mt-4"><ErrorNote>{err}</ErrorNote></div>
      <Link to="/" className="mt-6 block text-center text-sm text-bean-500 underline">Go to home</Link>
    </div>
  );
}
