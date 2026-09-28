import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CalendarClock, MessageCircle, RotateCcw, Sparkles, Timer } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useSession } from '@/context/SessionContext';
import { api } from '@/lib/api';
import { clock, dayClock, minutes, rupees } from '@/lib/format';
import { useLiveStats } from '@/lib/hooks';
import type { Order, Recommendation } from '@/lib/types';
import { ItemSheet } from '@/components/ItemSheet';
import { StatusPill } from '@/components/ui';
import { NudgeCard } from '@/components/Nudge';
import type { MenuItem } from '@/lib/types';

interface Welcome {
  greeting: string;
  loyalty: { points: number; tier: string; visits: number; nextTier: string | null; pointsToNext: number };
  context: { weather?: { summary: string; tempC: number }; partOfDay: string; headline: string };
}

export default function Home() {
  const { me } = useAuth();
  const { cafeId, addItem, menu } = useSession();
  const live = useLiveStats();
  const [orders, setOrders] = useState<Order[]>([]);
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [welcome, setWelcome] = useState<Welcome | null>(null);
  const [pick, setPick] = useState<{ item: MenuItem; preset?: Record<string, string> } | null>(null);

  useEffect(() => {
    api.get<Order[]>('/orders').then(setOrders).catch(() => undefined);
    api.get<Recommendation[]>(`/cafes/${cafeId}/recommendations?n=4`).then(setRecs).catch(() => undefined);
    api.get<Welcome>(`/cafes/${cafeId}/welcome`).then(setWelcome).catch(() => undefined);
  }, [cafeId]);

  const active = orders.filter((o) => ['scheduled', 'placed', 'in_progress', 'ready'].includes(o.status));
  const usual = me?.usuals?.[0];
  const hour = new Date().getHours();
  const hello = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

  return (
    <div className="space-y-6">
      <section>
        <p className="text-sm text-bean-500">{hello},</p>
        <h1 className="text-3xl">{me?.displayName?.split(' ')[0] ?? 'friend'}</h1>
        {welcome && (
          <p className="mt-1 text-sm text-bean-700">
            {welcome.context.weather && <span>{welcome.context.weather.summary}, {Math.round(welcome.context.weather.tempC)}°C · </span>}
            {welcome.context.headline}
          </p>
        )}
      </section>

      {welcome && (
        <Link to="/profile" className="card flex items-center justify-between bg-gradient-to-br from-bean-900 to-bean-700 px-4 py-3.5 text-cream-50">
          <div>
            <p className="text-[11px] tracking-wider text-bean-300 uppercase">{welcome.loyalty.tier} member</p>
            <p className="font-display text-2xl">{welcome.loyalty.points} <span className="text-sm font-sans text-bean-300">beans</span></p>
          </div>
          <p className="max-w-[55%] text-right text-xs text-bean-300">
            {welcome.loyalty.nextTier ? `${welcome.loyalty.pointsToNext} beans to ${welcome.loyalty.nextTier}` : 'Top tier. Thank you!'}
            <br />
            {welcome.loyalty.visits} visit{welcome.loyalty.visits === 1 ? '' : 's'}
          </p>
        </Link>
      )}

      {active.map((o) => (
        <Link key={o.id} to={`/orders/${o.id}`} className="card rise flex items-center gap-3 border-ember-500/40 bg-ember-100/60 px-4 py-3.5">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-white font-display text-lg text-ember-600">{o.pickupCode}</div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2"><StatusPill status={o.status} /></div>
            <p className="mt-0.5 truncate text-sm text-bean-700">
              {o.status === 'scheduled' && o.scheduledFor ? `Ready ${dayClock(o.scheduledFor)}` : o.status === 'ready' ? 'Collect at the counter' : o.eta ? `Ready around ${clock(o.eta.readyAt)}` : ''}
            </p>
          </div>
          <ArrowRight className="h-4 w-4 text-bean-500" />
        </Link>
      ))}

      <NudgeCard />

      <div className="grid grid-cols-2 gap-3">
        <Link to="/order" className="card flex flex-col gap-2 p-4">
          <MessageCircle className="h-5 w-5 text-ember-600" />
          <p className="font-medium">Chat to order</p>
          <p className="text-xs text-bean-500">"Something iced, not too sweet"</p>
        </Link>
        <Link to="/wait" className="card flex flex-col gap-2 p-4">
          <Timer className="h-5 w-5 text-ember-600" />
          <p className="font-medium">{live ? `~${minutes(live.currentWaitSec)} wait` : 'Wait times'}</p>
          <p className="text-xs text-bean-500">Best time to visit</p>
        </Link>
      </div>

      {usual && (
        <section className="card flex items-center gap-3 p-4">
          <RotateCcw className="h-5 w-5 text-bean-500" />
          <div className="min-w-0 flex-1">
            <p className="text-xs text-bean-500">Your usual</p>
            <p className="truncate font-medium">{usual.name}{usual.modifierLabels.length ? ` · ${usual.modifierLabels.join(', ')}` : ''}</p>
          </div>
          <button className="btn-primary px-3 py-2" onClick={() => addItem(usual.itemId, usual.modifiers)}>Add</button>
        </section>
      )}

      {recs.length > 0 && (
        <section>
          <div className="mb-3 flex items-end justify-between">
            <h2 className="flex items-center gap-1.5 text-xl"><Sparkles className="h-4 w-4 text-ember-500" /> Picked for you</h2>
            <Link to="/discover" className="text-sm font-medium text-ember-600">See all</Link>
          </div>
          <div className="-mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-1 scroll-thin">
            {recs.map((r) => (
              <button key={r.item.id} onClick={() => setPick({ item: r.item, preset: r.suggestedModifiers })} className="card w-56 shrink-0 snap-start p-4 text-left">
                <p className="text-[11px] font-medium tracking-wide text-bean-500 uppercase">{menu?.categories.find((c) => c.id === r.item.category)?.label}</p>
                <p className="mt-1 font-display text-lg leading-tight">{r.item.name}</p>
                <p className="mt-1.5 line-clamp-3 text-xs text-bean-700">{r.reason}</p>
                <p className="mt-3 text-sm font-semibold">{rupees(r.item.price)}</p>
              </button>
            ))}
          </div>
        </section>
      )}

      <Link to="/order" className="card flex items-center gap-3 p-4">
        <CalendarClock className="h-5 w-5 text-ember-600" />
        <div className="flex-1">
          <p className="font-medium">Pre-order for later</p>
          <p className="text-xs text-bean-500">Pick a time and it's fresh when you arrive</p>
        </div>
        <ArrowRight className="h-4 w-4 text-bean-500" />
      </Link>

      <ItemSheet item={pick?.item ?? null} preset={pick?.preset} onClose={() => setPick(null)} />
    </div>
  );
}
