import { useCallback, useEffect, useState } from 'react';
import { CloudSun, Heart, RefreshCw, Sparkles, X } from 'lucide-react';
import { api } from '@/lib/api';
import { useSession } from '@/context/SessionContext';
import { rupees } from '@/lib/format';
import type { MenuItem, Recommendation } from '@/lib/types';
import { ItemSheet } from '@/components/ItemSheet';
import { Empty, PageLoader } from '@/components/ui';

interface Ctx { headline: string; weather?: { summary: string; tempC: number } }

export default function Discover() {
  const { cafeId, menu } = useSession();
  const [recs, setRecs] = useState<Recommendation[] | null>(null);
  const [ctx, setCtx] = useState<Ctx | null>(null);
  const [liked, setLiked] = useState<Set<string>>(new Set());
  const [pick, setPick] = useState<{ item: MenuItem; preset?: Record<string, string> } | null>(null);

  const load = useCallback(() => {
    setRecs(null);
    api.get<Recommendation[]>(`/cafes/${cafeId}/recommendations?n=8`).then(setRecs).catch(() => setRecs([]));
  }, [cafeId]);
  useEffect(() => {
    load();
    api.get<{ context: Ctx }>(`/cafes/${cafeId}/welcome`).then((w) => setCtx(w.context)).catch(() => undefined);
  }, [load, cafeId]);

  const react = async (itemId: string, type: 'like' | 'dismiss') => {
    await api.post('/interactions', { itemId, type });
    if (type === 'like') setLiked(new Set(liked).add(itemId));
    else setRecs((r) => r?.filter((x) => x.item.id !== itemId) ?? null);
  };

  return (
    <div>
      <div className="mb-4 flex items-end justify-between">
        <div>
          <h1 className="text-3xl">Discover</h1>
          <p className="text-sm text-bean-500">Picked for your taste, the weather and the time of day.</p>
        </div>
        <button onClick={load} className="rounded-full p-2 text-bean-500 hover:bg-cream-200" aria-label="Refresh"><RefreshCw className="h-5 w-5" /></button>
      </div>
      {ctx && (
        <div className="mb-4 flex items-center gap-2 rounded-xl bg-honey-100 px-3 py-2 text-sm text-bean-800">
          <CloudSun className="h-4 w-4 shrink-0" />
          <span>{ctx.weather ? `${ctx.weather.summary}, ${Math.round(ctx.weather.tempC)}°C. ` : ''}{ctx.headline}</span>
        </div>
      )}
      {!recs ? <PageLoader /> : recs.length === 0 ? (
        <Empty icon={<Sparkles className="h-5 w-5" />} title="Nothing to suggest yet">Order a few times and this gets sharper.</Empty>
      ) : (
        <div className="grid gap-3">
          {recs.map((r, i) => (
            <div key={r.item.id} className="card rise p-4" style={{ animationDelay: `${i * 40}ms` }}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] font-medium tracking-wide text-bean-500 uppercase">{menu?.categories.find((c) => c.id === r.item.category)?.label}</p>
                  <h3 className="text-xl leading-tight">{r.item.name}</h3>
                </div>
                <span className="text-sm font-semibold">{rupees(r.item.price)}</span>
              </div>
              <p className="mt-2 flex gap-1.5 text-sm text-bean-700"><Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ember-500" />{r.reason}</p>
              {Object.keys(r.suggestedModifiers).length > 0 && (
                <p className="mt-1 text-xs text-bean-500">Suggested with {Object.values(r.suggestedModifiers).join(', ')} milk</p>
              )}
              <div className="mt-3 flex gap-2">
                <button className="btn-accent flex-1 py-2" onClick={() => setPick({ item: r.item, preset: r.suggestedModifiers })}>Add</button>
                <button className={`btn-ghost px-3 py-2 ${liked.has(r.item.id) ? 'text-berry-600' : ''}`} onClick={() => react(r.item.id, 'like')} aria-label="Like"><Heart className={`h-4 w-4 ${liked.has(r.item.id) ? 'fill-current' : ''}`} /></button>
                <button className="btn-ghost px-3 py-2" onClick={() => react(r.item.id, 'dismiss')} aria-label="Not for me"><X className="h-4 w-4" /></button>
              </div>
            </div>
          ))}
        </div>
      )}
      <ItemSheet item={pick?.item ?? null} preset={pick?.preset} onClose={() => setPick(null)} />
    </div>
  );
}
