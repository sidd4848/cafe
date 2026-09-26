import { useCallback, useEffect, useMemo, useState } from 'react';
import { collection, query, where } from 'firebase/firestore';
import { Armchair, Brush, Clock, Plus, Sparkles, UserCheck, Users, X } from 'lucide-react';
import { api } from '@/lib/api';
import { firestore } from '@/lib/firebase';
import { config } from '@/lib/config';
import { useAuth } from '@/context/AuthContext';
import { clock, minutes } from '@/lib/format';
import { useNow, useQuery } from '@/lib/hooks';
import { ErrorNote, Sheet } from '@/components/ui';

interface Table { id: string; label: string; seats: number; zone: string; status: 'free' | 'seated' | 'dirty'; partySize?: number; partyName?: string; serverName?: string; serverUid?: string; seatedAt?: string }
interface Party { id: string; name: string; size: number; seating: string; joinedAt: string; quotedWaitSec?: number; position?: number; source: string }
interface Server { id: string; name: string; onShift: boolean }
interface Suggestion { partyId: string; tableId: string | null; serverUid: string | null; wastedSeats: number | null }
interface FloorStats { dwellSec: Record<string, number> }

const ZONES = ['window', 'main', 'garden', 'bar'];
const STATUS_STYLE = { free: 'border-leaf-600/50 bg-leaf-100', seated: 'border-ember-500/50 bg-ember-100', dirty: 'border-honey-500/60 bg-honey-100' };

/** Host stand: live tables, waitlist with AI-suggested seating, servers on shift. */
export default function Floor() {
  const cafeId = config.cafeId;
  const { user } = useAuth();
  const now = useNow(30000);
  const tq = useMemo(() => collection(firestore, `cafes/${cafeId}/tables`), [cafeId]);
  const wq = useMemo(() => query(collection(firestore, `cafes/${cafeId}/waitlist`), where('status', '==', 'waiting')), [cafeId]);
  const sq = useMemo(() => query(collection(firestore, `cafes/${cafeId}/shift`), where('onShift', '==', true)), [cafeId]);
  const tables = useQuery<Table>(tq, `tables-${cafeId}`).data;
  const waitlist = useQuery<Party>(wq, `wl-${cafeId}`).data.sort((a, b) => a.joinedAt.localeCompare(b.joinedAt));
  const servers = useQuery<Server>(sq, `shift-${cafeId}`).data;
  const [suggest, setSuggest] = useState<Suggestion[]>([]);
  const [stats, setStats] = useState<FloorStats | null>(null);
  const [seatFor, setSeatFor] = useState<Table | null>(null);
  const [walkIn, setWalkIn] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api.get<{ suggestions: Suggestion[]; stats: FloorStats }>(`/staff/cafes/${cafeId}/floor`).then((r) => { setSuggest(r.suggestions); setStats(r.stats); }).catch(() => undefined);
  }, [cafeId]);
  const tableKey = tables.map((t) => t.status).join('');
  useEffect(refresh, [refresh, tableKey, waitlist.length, servers.length]);

  const call = async (p: Promise<unknown>) => {
    setErr(null);
    try { await p; } catch (e) { setErr((e as Error).message); }
  };
  const onShift = servers.some((s) => s.id === user?.uid);
  const serverName = (uid?: string | null) => servers.find((s) => s.id === uid)?.name;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-3xl">Floor</h1>
        {stats && <p className="text-xs text-bean-500">Learned table time: pairs {minutes(stats.dwellSec.small)} · 3–4 {minutes(stats.dwellSec.medium)} · 5+ {minutes(stats.dwellSec.large)}</p>}
        <button className={onShift ? 'btn-ghost' : 'btn-primary'} onClick={() => call(api.post(`/staff/cafes/${cafeId}/shift`, { onShift: !onShift }))}>
          <UserCheck className="h-4 w-4" /> {onShift ? 'Clock out' : 'Clock in as server'}
        </button>
      </div>
      <ErrorNote>{err}</ErrorNote>

      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <div className="space-y-4">
          {ZONES.map((zone) => {
            const zt = tables.filter((t) => t.zone === zone).sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
            if (!zt.length) return null;
            return (
              <section key={zone}>
                <h2 className="mb-2 font-sans text-xs font-semibold tracking-wider text-bean-500 uppercase">{zone}</h2>
                <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 xl:grid-cols-4">
                  {zt.map((t) => {
                    const mins = t.seatedAt ? Math.round((now - new Date(t.seatedAt).getTime()) / 60000) : 0;
                    return (
                      <div key={t.id} className={`rounded-2xl border-2 p-3 ${STATUS_STYLE[t.status]}`}>
                        <div className="flex items-center justify-between">
                          <p className="font-semibold">{t.label}</p>
                          <span className="flex items-center gap-0.5 text-xs text-bean-700"><Armchair className="h-3 w-3" />{t.seats}</span>
                        </div>
                        {t.status === 'seated' ? (
                          <p className="mt-1 text-xs text-bean-700">{t.partyName} · {t.partySize}p · {mins}m<br />{t.serverName ?? 'No server'}</p>
                        ) : (
                          <p className="mt-1 text-xs capitalize text-bean-700">{t.status === 'dirty' ? 'Needs clearing' : 'Free'}</p>
                        )}
                        <div className="mt-2">
                          {t.status === 'free' && <button className="btn-primary w-full py-1 text-xs" onClick={() => setSeatFor(t)}>Seat</button>}
                          {t.status === 'seated' && <button className="btn-ghost w-full py-1 text-xs" onClick={() => call(api.post(`/staff/cafes/${cafeId}/tables/${t.id}/clear`))}>Guests left</button>}
                          {t.status === 'dirty' && <button className="btn-ghost w-full py-1 text-xs" onClick={() => call(api.post(`/staff/cafes/${cafeId}/tables/${t.id}/ready`))}><Brush className="h-3 w-3" /> Cleared</button>}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>

        <aside className="space-y-3">
          <div className="card p-3">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="flex items-center gap-2 font-sans text-sm font-semibold"><Users className="h-4 w-4" /> Waitlist ({waitlist.length})</h2>
              <button className="btn-ghost px-2 py-1 text-xs" onClick={() => setWalkIn(true)}><Plus className="h-3.5 w-3.5" /> Walk-in</button>
            </div>
            <div className="space-y-2">
              {waitlist.map((p) => {
                const s = suggest.find((x) => x.partyId === p.id);
                const st = tables.find((t) => t.id === s?.tableId);
                return (
                  <div key={p.id} className="rounded-xl border border-cream-200 bg-white p-2.5 text-sm">
                    <div className="flex items-center gap-2">
                      <b>{p.name}</b><span className="text-xs text-bean-500">· {p.size}p{p.seating !== 'any' ? ` · ${p.seating.replace('_', ' ')}` : ''}{p.source === 'app' ? ' · app' : ''}</span>
                      <button className="ml-auto text-bean-300 hover:text-berry-600" onClick={() => call(api.del(`/staff/cafes/${cafeId}/waitlist/${p.id}`))} aria-label="Remove"><X className="h-3.5 w-3.5" /></button>
                    </div>
                    <p className="mt-0.5 flex items-center gap-1 text-xs text-bean-500"><Clock className="h-3 w-3" /> waiting {Math.round((now - new Date(p.joinedAt).getTime()) / 60000)}m · quoted {p.quotedWaitSec != null && p.quotedWaitSec >= 0 ? minutes(p.quotedWaitSec) : 'n/a'}</p>
                    {st ? (
                      <button className="btn-accent mt-2 w-full py-1.5 text-xs" onClick={() => call(api.post(`/staff/cafes/${cafeId}/tables/${st.id}/seat`, { partyId: p.id, serverUid: s?.serverUid }))}>
                        <Sparkles className="h-3.5 w-3.5" /> Seat at {st.label}{s?.serverUid ? ` with ${serverName(s.serverUid)}` : ''}
                      </button>
                    ) : <p className="mt-1.5 text-xs text-bean-500">No fitting table free yet</p>}
                  </div>
                );
              })}
              {waitlist.length === 0 && <p className="py-4 text-center text-xs text-bean-500">No one waiting</p>}
            </div>
          </div>
          <div className="card p-3">
            <h2 className="mb-2 font-sans text-sm font-semibold">Servers on shift</h2>
            {servers.length ? servers.map((s) => (
              <p key={s.id} className="flex justify-between text-sm"><span>{s.name}</span><span className="text-xs text-bean-500">{tables.filter((t) => t.serverUid === s.id && t.status === 'seated').length} tables</span></p>
            )) : <p className="text-xs text-bean-500">Nobody clocked in. Seating suggestions won't pick a server.</p>}
          </div>
        </aside>
      </div>

      <SeatSheet table={seatFor} waitlist={waitlist} servers={servers} onClose={() => setSeatFor(null)}
        onSeat={(body) => call(api.post(`/staff/cafes/${cafeId}/tables/${seatFor!.id}/seat`, body)).then(() => setSeatFor(null))} />
      <WalkInSheet open={walkIn} onClose={() => setWalkIn(false)} onAdd={(body) => call(api.post(`/staff/cafes/${cafeId}/waitlist`, body)).then(() => setWalkIn(false))} />
    </div>
  );
}

function SeatSheet({ table, waitlist, servers, onClose, onSeat }: { table: Table | null; waitlist: Party[]; servers: Server[]; onClose: () => void; onSeat: (b: object) => void }) {
  const [size, setSize] = useState(2);
  const [server, setServer] = useState('');
  if (!table) return null;
  const fitting = waitlist.filter((p) => p.size <= table.seats);
  return (
    <Sheet open onClose={onClose} title={`Seat ${table.label} (${table.seats})`}>
      <p className="label">Server</p>
      <select className="mb-4 w-full" value={server} onChange={(e) => setServer(e.target.value)}>
        <option value="">Unassigned</option>
        {servers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      {fitting.length > 0 && (
        <>
          <p className="label">From the waitlist</p>
          <div className="mb-4 space-y-2">
            {fitting.map((p) => (
              <button key={p.id} className="btn-ghost w-full justify-between" onClick={() => onSeat({ partyId: p.id, serverUid: server || null })}>
                <span>{p.name} · {p.size}p</span><span className="text-xs text-bean-500">since {clock(p.joinedAt)}</span>
              </button>
            ))}
          </div>
        </>
      )}
      <p className="label">Or a walk-in</p>
      <div className="flex gap-2">
        <select value={size} onChange={(e) => setSize(Number(e.target.value))}>{Array.from({ length: table.seats }, (_, i) => i + 1).map((n) => <option key={n}>{n}</option>)}</select>
        <button className="btn-primary flex-1" onClick={() => onSeat({ size, serverUid: server || null })}>Seat walk-in</button>
      </div>
    </Sheet>
  );
}

function WalkInSheet({ open, onClose, onAdd }: { open: boolean; onClose: () => void; onAdd: (b: object) => void }) {
  const [name, setName] = useState('');
  const [size, setSize] = useState(2);
  const [seating, setSeating] = useState('any');
  return (
    <Sheet open={open} onClose={onClose} title="Add to waitlist">
      <div className="space-y-3">
        <input className="w-full" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <div className="flex gap-2">
          <select className="flex-1" value={size} onChange={(e) => setSize(Number(e.target.value))}>{[1, 2, 3, 4, 5, 6, 7, 8].map((n) => <option key={n} value={n}>{n} people</option>)}</select>
          <select className="flex-1" value={seating} onChange={(e) => setSeating(e.target.value)}><option value="any">Any</option><option value="no_bar">Table only</option><option value="bar">Bar ok</option></select>
        </div>
        <button className="btn-accent w-full" onClick={() => onAdd({ name: name || 'Walk-in', size, seating })}>Add</button>
      </div>
    </Sheet>
  );
}
