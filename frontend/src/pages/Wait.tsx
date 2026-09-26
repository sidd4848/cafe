import { useEffect, useState } from 'react';
import { Car, Clock, Sparkles, Users } from 'lucide-react';
import { api } from '@/lib/api';
import { useSession } from '@/context/SessionContext';
import { clock, minutes } from '@/lib/format';
import { useLiveStats } from '@/lib/hooks';
import type { Slot } from '@/lib/types';
import { ErrorNote, PageLoader, Spinner } from '@/components/ui';
import { WaitlistCard } from '@/components/Waitlist';

interface BestTimes { date: string; slots: Slot[]; best: Slot[]; liveAdjustment: number }
interface Plan { arrivalAt: string; readyIfOrderedNow: string; suggestedPickupAt: string | null; advice: string }
interface TableWait { partySize: number; quotedWaitSec: number; freeNow: number; waitingParties: number }

const LEVEL = { quiet: 'bg-leaf-600', moderate: 'bg-honey-500', busy: 'bg-berry-600' };

export default function Wait() {
  const { cafeId, session, setPickup, setCheckoutOpen } = useSession();
  const live = useLiveStats();
  const [day, setDay] = useState<'today' | 'tomorrow'>('today');
  const [bt, setBt] = useState<BestTimes | null>(null);
  const [mins, setMins] = useState(15);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [planning, setPlanning] = useState(false);
  const [party, setParty] = useState(2);
  const [table, setTable] = useState<TableWait | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const d = new Date();
    if (day === 'tomorrow') d.setDate(d.getDate() + 1);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    setBt(null);
    api.get<BestTimes>(`/cafes/${cafeId}/best-times?date=${iso}`).then(setBt).catch(() => undefined);
  }, [cafeId, day, live?.activeOrders]);

  useEffect(() => {
    api.get<TableWait>(`/cafes/${cafeId}/table-wait?party=${party}`).then(setTable).catch(() => setTable(null));
  }, [cafeId, party, live?.updatedAt]);

  async function doPlan() {
    setPlanning(true);
    setErr(null);
    try {
      setPlan(await api.post<Plan>(`/cafes/${cafeId}/plan-arrival`, { minutesAway: mins }));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setPlanning(false);
    }
  }

  async function usePlan() {
    if (!plan) return;
    await setPickup(plan.suggestedPickupAt);
    setCheckoutOpen(true);
  }

  const max = bt ? Math.max(...bt.slots.map((s) => s.expectedWaitSec), 300) : 1;
  return (
    <div className="space-y-5">
      <h1 className="text-3xl">Wait times</h1>

      <div className="grid grid-cols-2 gap-3">
        <div className="card p-4">
          <p className="flex items-center gap-1.5 text-xs text-bean-500"><Clock className="h-3.5 w-3.5" /> Takeaway now</p>
          <p className="mt-1 font-display text-4xl">{live ? minutes(live.currentWaitSec) : '–'}</p>
          <p className="text-xs text-bean-500">{live ? `${live.activeOrders} orders · ${live.baristasOnShift} baristas` : ''}</p>
        </div>
        <div className="card p-4">
          <p className="flex items-center gap-1.5 text-xs text-bean-500"><Users className="h-3.5 w-3.5" /> Table for
            <select className="ml-1 rounded-md border-cream-300 px-1 py-0 text-xs" value={party} onChange={(e) => setParty(Number(e.target.value))}>
              {[1, 2, 3, 4, 5, 6].map((n) => <option key={n}>{n}</option>)}
            </select>
          </p>
          <p className="mt-1 font-display text-4xl">{table ? (table.quotedWaitSec < 60 ? 'Now' : minutes(table.quotedWaitSec)) : '–'}</p>
          <p className="text-xs text-bean-500">{table ? `${table.freeNow} free · ${table.waitingParties} waiting` : ''}</p>
        </div>
      </div>

      <WaitlistCard cafeId={cafeId} party={party} setParty={setParty} />

      <section className="card p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xl">Best time to visit</h2>
          <div className="flex rounded-lg bg-cream-200 p-0.5 text-xs font-medium">
            {(['today', 'tomorrow'] as const).map((d) => (
              <button key={d} onClick={() => setDay(d)} className={`rounded-md px-2.5 py-1 capitalize ${day === d ? 'bg-cream-50 shadow-sm' : 'text-bean-500'}`}>{d}</button>
            ))}
          </div>
        </div>
        {!bt ? <PageLoader /> : (
          <>
            <div className="flex h-32 items-end gap-[3px]" role="img" aria-label="Expected wait through the day">
              {bt.slots.map((s) => (
                <div key={s.start} className="group relative flex-1">
                  <div className={`w-full rounded-t ${LEVEL[s.level]} opacity-80 group-hover:opacity-100`} style={{ height: `${Math.max(6, (s.expectedWaitSec / max) * 120)}px` }} />
                  <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 rounded-md bg-bean-900 px-2 py-1 text-[11px] whitespace-nowrap text-cream-50 group-hover:block">
                    {clock(s.start)} · ~{minutes(s.expectedWaitSec)}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-1 flex justify-between text-[10px] text-bean-500">
              <span>{bt.slots[0] && clock(bt.slots[0].start)}</span>
              <span>{bt.slots.at(-1) && clock(bt.slots.at(-1)!.start)}</span>
            </div>
            {bt.best.length > 0 && (
              <div className="mt-3 rounded-xl bg-leaf-100 px-3 py-2 text-sm text-leaf-600">
                <Sparkles className="mr-1 inline h-3.5 w-3.5" />
                Quietest: {bt.best.map((b) => `${clock(b.start)} (~${minutes(b.expectedWaitSec)})`).join(', ')}
              </div>
            )}
            {day === 'today' && bt.liveAdjustment !== 1 && (
              <p className="mt-2 text-xs text-bean-500">
                Adjusted live: the bar is running {bt.liveAdjustment > 1 ? 'busier' : 'quieter'} than usual right now.
              </p>
            )}
          </>
        )}
      </section>

      <section className="card p-4">
        <h2 className="flex items-center gap-2 text-xl"><Car className="h-5 w-5 text-ember-600" /> Ready when I arrive</h2>
        <p className="mt-1 text-sm text-bean-500">Tell us how far away you are. We'll time your order so it's fresh, not waiting.</p>
        <div className="mt-3 flex items-center gap-3">
          <input type="range" min={0} max={90} step={5} value={mins} onChange={(e) => setMins(Number(e.target.value))} className="flex-1 border-0 p-0 accent-[#b85a2e]" />
          <span className="w-16 text-right font-semibold">{mins} min</span>
        </div>
        <button className="btn-primary mt-3 w-full" onClick={doPlan} disabled={planning}>{planning && <Spinner className="h-4 w-4 text-white" />} Plan it</button>
        <ErrorNote>{err}</ErrorNote>
        {plan && (
          <div className="rise mt-3 rounded-xl bg-cream-200 p-3 text-sm">
            <p>{plan.advice}</p>
            <p className="mt-1 text-xs text-bean-500">You arrive ~{clock(plan.arrivalAt)} · if ordered now, ready ~{clock(plan.readyIfOrderedNow)}</p>
            <button className="btn-accent mt-2 w-full py-2" onClick={usePlan} disabled={!session?.cart.length}>
              {session?.cart.length ? (plan.suggestedPickupAt ? `Pre-order for ${clock(plan.suggestedPickupAt)}` : 'Order now') : 'Add something to your cart first'}
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
