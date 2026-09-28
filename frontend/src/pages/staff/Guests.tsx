import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Crown, Megaphone, Search, Sparkles, UserRound } from 'lucide-react';
import { api } from '@/lib/api';
import { config } from '@/lib/config';
import { clock, dayClock, rupees } from '@/lib/format';
import { ErrorNote, PageLoader, Sheet, Spinner } from '@/components/ui';

interface Guest {
  uid: string; name: string; email: string; tier: string; points: number; visits: number; orders: number;
  lifetimeSpend: number; avgTicket: number; lastOrderAt: string | null; daysSinceLastOrder: number | null;
  habitTime: string | null; habitSpreadMin: number | null; shiftPropensity: number;
  usual: { name: string; modifierLabels: string[] } | null; diet: string; avoid: string[];
  taste: Record<string, string | number | null>; segments: string[];
}
interface Detail extends Guest {
  recentOrders: { id: string; at: string; total: number; status: string; items: string[] }[];
  offers: { day: string; beans: number; status: string; context: string; toAt: string }[];
}

const SEG: Record<string, { label: string; hint: string }> = {
  peak_regular: { label: 'Rush regulars', hint: 'Usually come during the forecast rush' },
  flexible: { label: 'Flexible', hint: 'Likely to shift for a small bonus' },
  lapsing: { label: 'Lapsing', hint: '3+ visits, none in 14 days' },
  vip: { label: 'VIP', hint: 'Reserve tier' },
  new: { label: 'New', hint: '1–2 visits' },
};

/** Guest profiles for employees, and one-tap targeting of a segment with an off-peak offer. */
export default function Guests() {
  const cafeId = config.cafeId;
  const [segment, setSegment] = useState<string | null>(null);
  const [data, setData] = useState<{ guests: Guest[]; segmentCounts: Record<string, number> | null; peaks: string[] } | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [q, setQ] = useState('');
  const [open, setOpen] = useState<Detail | null>(null);
  const [campaign, setCampaign] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    setData(null);
    api.get<NonNullable<typeof data>>(`/staff/cafes/${cafeId}/guests${segment ? `?segment=${segment}` : ''}`)
      .then((d) => { setData(d); if (d.segmentCounts) setCounts(d.segmentCounts); })
      .catch((e) => setErr(e.message));
  }, [cafeId, segment]);
  useEffect(() => { load(); }, [load]);

  const openGuest = (uid: string) => api.get<Detail>(`/staff/cafes/${cafeId}/guests/${uid}`).then(setOpen).catch((e) => setErr(e.message));
  const list = (data?.guests ?? []).filter((g) => !q || `${g.name} ${g.email}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="mr-auto">
          <h1 className="text-3xl">Guests</h1>
          <p className="text-sm text-bean-500">Who your regulars are, when they come, what they like, and who to move out of the rush{data?.peaks.length ? ` (${data.peaks.join(', ')} today)` : ''}.</p>
        </div>
        <button className="btn-accent" onClick={() => setCampaign(true)}><Megaphone className="h-4 w-4" /> Target a segment</button>
      </div>
      <ErrorNote>{err}</ErrorNote>

      <div className="flex flex-wrap gap-2">
        <button onClick={() => setSegment(null)} className={`chip ${!segment ? 'chip-on' : ''}`}>All</button>
        {Object.entries(SEG).map(([id, s]) => (
          <button key={id} onClick={() => setSegment(id)} title={s.hint} className={`chip ${segment === id ? 'chip-on' : ''}`}>{s.label}{counts[id] != null ? ` · ${counts[id]}` : ''}</button>
        ))}
        <label className="relative ml-auto">
          <Search className="absolute top-2.5 left-2.5 h-4 w-4 text-bean-300" />
          <input className="w-52 py-1.5 pl-8" placeholder="Search guests" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
      </div>

      {!data ? <PageLoader /> : list.length === 0 ? <p className="card p-8 text-center text-sm text-bean-500">No guests in this segment yet.</p> : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="border-b border-cream-200 text-left text-xs text-bean-500 uppercase">
              <tr><th className="px-4 py-2">Guest</th><th>Tier</th><th>Visits</th><th>Spend</th><th>Usual time</th><th>Usual order</th><th>Diet</th><th>Shift chance</th></tr>
            </thead>
            <tbody className="divide-y divide-cream-200">
              {list.map((g) => (
                <tr key={g.uid} className="cursor-pointer hover:bg-cream-100" onClick={() => openGuest(g.uid)}>
                  <td className="px-4 py-2.5"><p className="font-medium">{g.name}</p><p className="text-xs text-bean-500">{g.email}</p></td>
                  <td><TierBadge tier={g.tier} /></td>
                  <td>{g.visits}</td>
                  <td>{rupees(g.lifetimeSpend)}</td>
                  <td>{g.habitTime ?? '–'}{g.segments.includes('peak_regular') && <span className="ml-1 rounded bg-berry-100 px-1 text-[10px] font-bold text-berry-600">RUSH</span>}</td>
                  <td className="max-w-[180px] truncate">{g.usual?.name ?? '–'}</td>
                  <td>{g.avoid.length || g.diet !== 'any' ? <span className="text-xs"><AlertTriangle className="mr-0.5 inline h-3 w-3 text-honey-500" />{[g.diet !== 'any' ? g.diet : null, ...g.avoid.map((a) => `no ${a}`)].filter(Boolean).join(', ')}</span> : '–'}</td>
                  <td><PropBar v={g.shiftPropensity} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Sheet open={!!open} onClose={() => setOpen(null)} title={open?.name ?? ''}>
        {open && (
          <div className="space-y-4 text-sm">
            <div className="flex items-center gap-2"><TierBadge tier={open.tier} /><span className="text-bean-500">{open.points} beans · {open.visits} visits · avg {rupees(open.avgTicket)}</span></div>
            <div className="flex flex-wrap gap-1">{open.segments.map((s) => <span key={s} className="chip">{SEG[s]?.label ?? s}</span>)}</div>
            <div className="grid grid-cols-2 gap-2">
              <Info label="Usual time" value={open.habitTime ? `${open.habitTime} (±${open.habitSpreadMin}m)` : '–'} />
              <Info label="Last visit" value={open.lastOrderAt ? dayClock(open.lastOrderAt) : '–'} />
              <Info label="Usual order" value={open.usual ? `${open.usual.name}${open.usual.modifierLabels.length ? ` · ${open.usual.modifierLabels.join(', ')}` : ''}` : '–'} />
              <Info label="Diet / allergens" value={[open.diet !== 'any' ? open.diet : null, ...open.avoid.map((a) => `no ${a}`)].filter(Boolean).join(', ') || 'none'} />
              <Info label="Taste" value={Object.entries(open.taste).filter(([, v]) => v != null).map(([k, v]) => `${k}: ${v}`).join(' · ') || '–'} />
              <Info label="Shift chance" value={`${Math.round(open.shiftPropensity * 100)}%`} />
            </div>
            <div>
              <p className="label">Recent orders</p>
              <ul className="space-y-1">{open.recentOrders.map((o) => <li key={o.id} className="flex justify-between gap-2"><span className="truncate">{o.items.join(', ')}</span><span className="text-bean-500">{dayClock(o.at)}</span></li>)}</ul>
            </div>
            <div>
              <p className="label">Offers</p>
              {open.offers.length ? <ul className="space-y-1">{open.offers.map((n, i) => <li key={i} className="flex justify-between"><span>{n.day} · pick up {clock(n.toAt)} · +{n.beans}</span><span className="capitalize text-bean-500">{n.status}</span></li>)}</ul> : <p className="text-bean-500">None yet</p>}
            </div>
          </div>
        )}
      </Sheet>

      <CampaignSheet open={campaign} counts={counts} onClose={() => setCampaign(false)} cafeId={cafeId} />
    </div>
  );
}

function CampaignSheet({ open, onClose, counts, cafeId }: { open: boolean; onClose: () => void; counts: Record<string, number>; cafeId: string }) {
  const [segment, setSegment] = useState('peak_regular');
  const [beans, setBeans] = useState(20);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function send() {
    setBusy(true);
    setErr(null);
    setResult(null);
    try {
      const r = await api.post<{ sent: number; skipped: number; peak: { start: string; end: string } }>(`/staff/cafes/${cafeId}/campaigns`, { segment, beans });
      setResult(`Sent ${r.sent} offer${r.sent === 1 ? '' : 's'} to move out of the ${clock(r.peak.start)}–${clock(r.peak.end)} rush${r.skipped ? ` (${r.skipped} skipped: already offered today or no quiet slot nearby)` : ''}.`);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Sheet open={open} onClose={onClose} title="Target a segment">
      <p className="-mt-2 mb-3 text-sm text-bean-500">Guests see a personal "beat the rush" offer in the app: pick up in a quieter slot and earn bonus beans.</p>
      <p className="label">Who</p>
      <div className="mb-4 grid gap-2">
        {Object.entries(SEG).map(([id, s]) => (
          <button key={id} onClick={() => setSegment(id)} className={`card flex items-center justify-between px-3 py-2.5 text-left text-sm ${segment === id ? 'border-bean-900 ring-1 ring-bean-900' : ''}`}>
            <span><b>{s.label}</b><span className="block text-xs text-bean-500">{s.hint}</span></span>
            <span className="text-bean-500">{counts[id] ?? 0}</span>
          </button>
        ))}
      </div>
      <p className="label">Bonus</p>
      <div className="mb-4 flex gap-2">{[10, 20, 30, 40].map((b) => <button key={b} onClick={() => setBeans(b)} className={`chip py-1.5 ${beans === b ? 'chip-on' : ''}`}>+{b} beans</button>)}</div>
      <ErrorNote>{err}</ErrorNote>
      {result && <p className="mb-2 rounded-xl bg-leaf-100 px-3 py-2 text-sm text-leaf-600">{result}</p>}
      <button className="btn-accent w-full" disabled={busy} onClick={send}>{busy ? <Spinner className="h-4 w-4 text-white" /> : <Sparkles className="h-4 w-4" />} Send offers</button>
    </Sheet>
  );
}

function TierBadge({ tier }: { tier: string }) {
  const style = tier === 'Reserve' ? 'bg-bean-900 text-cream-50' : tier === 'Roast' ? 'bg-ember-100 text-ember-600' : 'bg-cream-200 text-bean-700';
  return <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${style}`}>{tier === 'Reserve' ? <Crown className="h-3 w-3" /> : <UserRound className="h-3 w-3" />}{tier}</span>;
}
function PropBar({ v }: { v: number }) {
  return <div className="flex items-center gap-1.5"><div className="h-1.5 w-16 rounded-full bg-cream-200"><div className="h-full rounded-full bg-leaf-600" style={{ width: `${Math.round(v * 100)}%` }} /></div><span className="text-xs text-bean-500">{Math.round(v * 100)}%</span></div>;
}
function Info({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl bg-cream-100 p-2.5"><p className="text-[11px] text-bean-500 uppercase">{label}</p><p className="mt-0.5">{value}</p></div>;
}
