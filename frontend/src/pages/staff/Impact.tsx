import { useCallback, useEffect, useState } from 'react';
import { ArrowDownRight, ArrowUpRight, Beaker, Coins, Footprints, Timer, TrendingUp, Trash2 } from 'lucide-react';
import { api } from '@/lib/api';
import { config } from '@/lib/config';
import { useAuth } from '@/context/AuthContext';
import { clock, minutes, rupees } from '@/lib/format';
import { ErrorNote, PageLoader, Spinner } from '@/components/ui';

interface Slot { start: string; expectedWaitSec: number; kind: 'peak' | 'quiet' | 'normal' }
interface Forecast { date: string; slots: Slot[]; peaks: { start: string; end: string; maxWaitSec: number }[]; thresholds: { peakWaitSec: number } }
interface Period { days: number; ordersPerDay: number; peakShare: number | null; peakWaitSec: number | null; walkoutsPerDay: number; avgTicket: number }
interface Impact {
  since: string; demoData: boolean; before: Period; after: Period;
  walkoutsAvoidedPerDay: number; revenueRecoveredPerDay: number; revenueRecoveredPerMonth: number;
  nudges: { offered: number; accepted: number; redeemed: number; beans: number; acceptRate: number | null };
  arms: { beans: number; offered: number; accepted: number; rate: number | null }[];
}

const pct = (v: number | null | undefined) => (v == null ? '–' : `${Math.round(v * 100)}%`);

/** The owner-facing story: where the rush is, how much of it we moved, what it earned. */
export default function ImpactPage() {
  const cafeId = config.cafeId;
  const { me } = useAuth();
  const [day, setDay] = useState<'today' | 'tomorrow'>('tomorrow');
  const [fc, setFc] = useState<Forecast | null>(null);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const loadImpact = useCallback(() => api.get<Impact>(`/staff/cafes/${cafeId}/impact`).then(setImpact).catch((e) => setErr(e.message)), [cafeId]);
  useEffect(() => { loadImpact(); }, [loadImpact]);
  useEffect(() => {
    const d = new Date();
    if (day === 'tomorrow') d.setDate(d.getDate() + 1);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    setFc(null);
    api.get<Forecast>(`/staff/cafes/${cafeId}/forecast?date=${iso}`).then(setFc).catch((e) => setErr(e.message));
  }, [cafeId, day]);

  async function demo(action: 'simulate' | 'clear') {
    setBusy(action);
    setErr(null);
    try {
      if (action === 'simulate') await api.post(`/staff/cafes/${cafeId}/demo`);
      else await api.del(`/staff/cafes/${cafeId}/demo`);
      setImpact(null);
      await loadImpact();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const max = fc ? Math.max(...fc.slots.map((s) => s.expectedWaitSec), 420) : 1;
  const b = impact?.before;
  const a = impact?.after;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div className="mr-auto">
          <h1 className="text-3xl">Peak impact</h1>
          <p className="text-sm text-bean-500">We forecast your rush, move flexible regulars into quiet slots with bonus beans, and fill barista idle time with pre-orders.</p>
        </div>
        {me?.role === 'manager' && (
          <div className="flex gap-2">
            <button className="btn-ghost" disabled={!!busy} onClick={() => demo('simulate')}>{busy === 'simulate' ? <Spinner className="h-4 w-4" /> : <Beaker className="h-4 w-4" />} Simulate 2 weeks</button>
            {impact?.demoData && <button className="btn-ghost text-berry-600" disabled={!!busy} onClick={() => demo('clear')}>{busy === 'clear' ? <Spinner className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />} Clear demo</button>}
          </div>
        )}
      </div>
      <ErrorNote>{err}</ErrorNote>
      {impact?.demoData && <p className="rounded-xl bg-honey-100 px-3 py-2 text-sm text-bean-800">Showing <b>simulated</b> data for demos. Clear it before going live.</p>}

      {!impact ? <PageLoader /> : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi icon={Coins} label="Revenue recovered / month" value={rupees(impact.revenueRecoveredPerMonth)} hint={`${rupees(impact.revenueRecoveredPerDay)} per day`} good />
            <Kpi icon={Footprints} label="Walk-outs avoided / day" value={String(impact.walkoutsAvoidedPerDay)} hint={`${b?.walkoutsPerDay ?? '–'} → ${a?.walkoutsPerDay ?? '–'} est. lost guests`} good />
            <Kpi icon={Timer} label="Wait in the rush" value={a?.peakWaitSec ? minutes(a.peakWaitSec) : '–'} hint={`was ${b?.peakWaitSec ? minutes(b.peakWaitSec) : '–'}`} delta={b?.peakWaitSec && a?.peakWaitSec ? (a.peakWaitSec - b.peakWaitSec) / b.peakWaitSec : null} lowerIsBetter />
            <Kpi icon={TrendingUp} label="Share of orders in peak" value={pct(a?.peakShare)} hint={`was ${pct(b?.peakShare)}`} delta={b?.peakShare && a?.peakShare ? (a.peakShare - b.peakShare) / b.peakShare : null} lowerIsBetter />
          </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
            <section className="card p-4">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-xl">Rush forecast</h2>
                <div className="flex rounded-lg bg-cream-200 p-0.5 text-xs font-medium">
                  {(['today', 'tomorrow'] as const).map((d) => (
                    <button key={d} onClick={() => setDay(d)} className={`rounded-md px-2.5 py-1 capitalize ${day === d ? 'bg-cream-50 shadow-sm' : 'text-bean-500'}`}>{d}</button>
                  ))}
                </div>
              </div>
              {!fc ? <PageLoader /> : (
                <>
                  <div className="relative flex h-40 items-end gap-[3px]" role="img" aria-label="Expected wait by half hour">
                    <div className="absolute inset-x-0 border-t border-dashed border-berry-600/60" style={{ bottom: `${(fc.thresholds.peakWaitSec / max) * 150}px` }}>
                      <span className="absolute -top-4 right-0 text-[10px] text-berry-600">rush line {minutes(fc.thresholds.peakWaitSec)}</span>
                    </div>
                    {fc.slots.map((s) => (
                      <div key={s.start} className="group relative flex-1">
                        <div className={`w-full rounded-t ${s.kind === 'peak' ? 'bg-berry-600' : s.kind === 'quiet' ? 'bg-leaf-600' : 'bg-honey-500'} opacity-80 group-hover:opacity-100`} style={{ height: `${Math.max(6, (s.expectedWaitSec / max) * 150)}px` }} />
                        <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 rounded-md bg-bean-900 px-2 py-1 text-[11px] whitespace-nowrap text-cream-50 group-hover:block">{clock(s.start)} · ~{minutes(s.expectedWaitSec)}</div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-1 flex justify-between text-[10px] text-bean-500"><span>{fc.slots[0] && clock(fc.slots[0].start)}</span><span>{fc.slots.at(-1) && clock(fc.slots.at(-1)!.start)}</span></div>
                  <p className="mt-3 text-sm">
                    {fc.peaks.length ? <>Rush expected <b>{fc.peaks.map((p) => `${clock(p.start)}–${clock(p.end)}`).join(', ')}</b>. Offers go out automatically to regulars who usually come then; you can also target a segment from <b>Guests</b>.</> : 'No rush forecast. Nothing to shift.'}
                  </p>
                </>
              )}
            </section>

            <section className="card p-4">
              <h2 className="mb-2 text-xl">Offers</h2>
              <div className="grid grid-cols-3 gap-2 text-center">
                <Stat label="Offered" value={impact.nudges.offered} />
                <Stat label="Accepted" value={impact.nudges.accepted} />
                <Stat label="Redeemed" value={impact.nudges.redeemed} />
              </div>
              <p className="mt-2 text-sm text-bean-700">Acceptance <b>{pct(impact.nudges.acceptRate)}</b> · {impact.nudges.beans} bonus beans paid</p>
              <p className="label mt-4">Incentive learning</p>
              <div className="space-y-1.5">
                {impact.arms.map((arm) => (
                  <div key={arm.beans} className="flex items-center gap-2 text-sm">
                    <span className="w-16">+{arm.beans} beans</span>
                    <div className="h-2 flex-1 rounded-full bg-cream-200"><div className="h-full rounded-full bg-ember-500" style={{ width: pct(arm.rate ?? 0) }} /></div>
                    <span className="w-24 text-right text-xs text-bean-500">{pct(arm.rate)} of {arm.offered}</span>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[11px] text-bean-500">The engine keeps testing bonus sizes and favours the one that moves the most guests per bean spent.</p>
            </section>
          </div>

          <section className="card overflow-x-auto p-4">
            <h2 className="mb-2 text-xl">Before vs after</h2>
            <table className="w-full min-w-[480px] text-sm">
              <thead className="text-left text-xs text-bean-500 uppercase"><tr><th className="py-1.5">Metric</th><th>Before</th><th>After</th></tr></thead>
              <tbody className="divide-y divide-cream-200">
                {[
                  ['Orders / day', b?.ordersPerDay, a?.ordersPerDay],
                  ['Share of orders in rush hours', pct(b?.peakShare), pct(a?.peakShare)],
                  ['Median wait in rush', b?.peakWaitSec ? minutes(b.peakWaitSec) : '–', a?.peakWaitSec ? minutes(a.peakWaitSec) : '–'],
                  ['Est. walk-outs / day', b?.walkoutsPerDay, a?.walkoutsPerDay],
                  ['Average ticket', b ? rupees(b.avgTicket) : '–', a ? rupees(a.avgTicket) : '–'],
                ].map(([k, x, y]) => <tr key={String(k)}><td className="py-2">{k}</td><td>{x ?? '–'}</td><td className="font-semibold">{y ?? '–'}</td></tr>)}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-bean-500">"Before" = the {b?.days ?? 0} days before the engine started ({new Date(impact.since).toLocaleDateString()}). Walk-outs are estimated from a wait-sensitivity curve; revenue recovered = walk-outs avoided × average ticket.</p>
          </section>
        </>
      )}
    </div>
  );
}

function Kpi({ icon: Icon, label, value, hint, delta, lowerIsBetter, good }: { icon: typeof Coins; label: string; value: string; hint: string; delta?: number | null; lowerIsBetter?: boolean; good?: boolean }) {
  const improved = delta != null ? (lowerIsBetter ? delta < 0 : delta > 0) : good;
  return (
    <div className="card p-4">
      <p className="flex items-center gap-1.5 text-xs text-bean-500"><Icon className="h-3.5 w-3.5" /> {label}</p>
      <p className="mt-1 font-display text-3xl">{value}</p>
      <p className="flex items-center gap-1 text-xs text-bean-500">
        {delta != null && (improved ? <ArrowDownRight className={`h-3.5 w-3.5 ${lowerIsBetter ? 'text-leaf-600' : 'rotate-[-90deg] text-leaf-600'}`} /> : <ArrowUpRight className="h-3.5 w-3.5 text-berry-600" />)}
        {delta != null && <span className={improved ? 'text-leaf-600' : 'text-berry-600'}>{Math.abs(Math.round(delta * 100))}%</span>} {hint}
      </p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return <div className="rounded-xl bg-cream-200 py-2"><p className="font-display text-2xl">{value}</p><p className="text-[11px] text-bean-500">{label}</p></div>;
}
