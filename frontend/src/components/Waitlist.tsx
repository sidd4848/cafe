import { useEffect, useState } from 'react';
import { Armchair, X } from 'lucide-react';
import { api } from '@/lib/api';
import { clock, minutes } from '@/lib/format';
import { useDoc } from '@/lib/hooks';
import { ErrorNote, Spinner } from './ui';

interface Entry { id: string; name: string; size: number; status: 'waiting' | 'seated' | 'left'; position?: number; quotedWaitSec?: number; estimatedSeatAt?: string; tableId?: string }

/** Digital queue for a table: join from anywhere, then watch your place update live. */
export function WaitlistCard({ cafeId, party, setParty }: { cafeId: string; party: number; setParty: (n: number) => void }) {
  const [entryId, setEntryId] = useState<string | null>(null);
  const [seating, setSeating] = useState('any');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { data: entry } = useDoc<Entry>(entryId ? `cafes/${cafeId}/waitlist/${entryId}` : null);

  useEffect(() => {
    api.get<Entry | null>(`/cafes/${cafeId}/waitlist/me`).then((e) => setEntryId(e?.id ?? null)).catch(() => undefined);
  }, [cafeId]);

  async function join() {
    setBusy(true);
    setErr(null);
    try {
      const e = await api.post<Entry>(`/cafes/${cafeId}/waitlist`, { size: party, seating });
      setEntryId(e.id);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function leave() {
    if (!entryId) return;
    await api.del(`/cafes/${cafeId}/waitlist/${entryId}`);
    setEntryId(null);
  }

  const active = entry && entry.status !== 'left';
  return (
    <section className="card p-4">
      <h2 className="flex items-center gap-2 text-xl"><Armchair className="h-5 w-5 text-ember-600" /> Get a table</h2>
      {active ? (
        entry.status === 'seated' ? (
          <p className="mt-2 rounded-xl bg-leaf-100 px-3 py-2 text-sm text-leaf-600">Your table is ready: <b>{entry.tableId}</b>. Head in!</p>
        ) : (
          <div className="rise mt-2">
            <div className="flex items-end justify-between">
              <div>
                <p className="text-sm text-bean-500">You're #{entry.position ?? '…'} in line · party of {entry.size}</p>
                <p className="font-display text-3xl">{entry.quotedWaitSec == null ? '…' : entry.quotedWaitSec < 60 ? 'Any moment' : `~${minutes(entry.quotedWaitSec)}`}</p>
                {entry.estimatedSeatAt && <p className="text-xs text-bean-500">around {clock(entry.estimatedSeatAt)} · updates live</p>}
              </div>
              <button className="btn-ghost px-3 py-2 text-berry-600" onClick={leave}><X className="h-4 w-4" /> Leave</button>
            </div>
          </div>
        )
      ) : (
        <>
          <p className="mt-1 text-sm text-bean-500">Join the queue from wherever you are. We'll quote a time from how fast tables are turning.</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <select className="py-2" value={party} onChange={(e) => setParty(Number(e.target.value))}>
              {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => <option key={n} value={n}>{n} {n === 1 ? 'person' : 'people'}</option>)}
            </select>
            <select className="py-2" value={seating} onChange={(e) => setSeating(e.target.value)}>
              <option value="any">Any seat</option>
              <option value="no_bar">Table only</option>
              <option value="bar">Bar is fine</option>
            </select>
            <button className="btn-primary flex-1" disabled={busy} onClick={join}>{busy && <Spinner className="h-4 w-4 text-white" />} Join waitlist</button>
          </div>
        </>
      )}
      <ErrorNote>{err}</ErrorNote>
    </section>
  );
}
