import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Award, ChevronRight, LogOut, Receipt, SlidersHorizontal, Store } from 'lucide-react';
import { isStaffRole, useAuth } from '@/context/AuthContext';
import { useSession } from '@/context/SessionContext';
import { api } from '@/lib/api';
import { rupees } from '@/lib/format';

interface Loyalty { points: number; tier: string; visits: number; lifetimeSpend: number; avgTicket: number; nextTier: string | null; pointsToNext: number; perks: string[] }

export default function Profile() {
  const { me, signOut } = useAuth();
  const { cafeId } = useSession();
  const [loyalty, setLoyalty] = useState<Loyalty | null>(null);
  useEffect(() => {
    api.get<{ loyalty: Loyalty }>(`/cafes/${cafeId}/welcome`).then((w) => setLoyalty(w.loyalty)).catch(() => undefined);
  }, [cafeId]);

  const p = me?.prefs ?? {};
  const facts = [
    p.temperature && `${p.temperature} drinks`,
    p.caffeine && `${p.caffeine} caffeine`,
    p.milk && (p.milk === 'none' ? 'black' : `${p.milk} milk`),
    p.diet && p.diet !== 'any' && p.diet,
    ...(p.avoid ?? []).map((a) => `no ${a}`),
    ...(p.flavours ?? []),
  ].filter(Boolean) as string[];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        {me?.photoURL ? <img src={me.photoURL} className="h-14 w-14 rounded-full" alt="" /> : <div className="grid h-14 w-14 place-items-center rounded-full bg-bean-900 font-display text-2xl text-cream-50">{me?.displayName?.[0]}</div>}
        <div>
          <h1 className="text-2xl">{me?.displayName}</h1>
          <p className="text-sm text-bean-500">{me?.email}</p>
        </div>
      </div>

      {loyalty && (
        <div className="card overflow-hidden">
          <div className="bg-gradient-to-br from-bean-900 to-bean-700 p-4 text-cream-50">
            <p className="flex items-center gap-1.5 text-xs tracking-wider text-bean-300 uppercase"><Award className="h-3.5 w-3.5" /> {loyalty.tier}</p>
            <p className="font-display text-4xl">{loyalty.points} <span className="font-sans text-sm text-bean-300">beans</span></p>
            {loyalty.nextTier && (
              <div className="mt-2 h-1.5 rounded-full bg-bean-800">
                <div className="h-full rounded-full bg-ember-500" style={{ width: `${Math.min(100, (loyalty.points / (loyalty.points + loyalty.pointsToNext)) * 100)}%` }} />
              </div>
            )}
            <p className="mt-1 text-xs text-bean-300">{loyalty.nextTier ? `${loyalty.pointsToNext} beans to ${loyalty.nextTier}` : 'Top tier'}</p>
          </div>
          <div className="grid grid-cols-3 divide-x divide-cream-200 text-center text-sm">
            <div className="p-3"><p className="font-semibold">{loyalty.visits}</p><p className="text-xs text-bean-500">visits</p></div>
            <div className="p-3"><p className="font-semibold">{rupees(loyalty.lifetimeSpend)}</p><p className="text-xs text-bean-500">spent</p></div>
            <div className="p-3"><p className="font-semibold">{rupees(loyalty.avgTicket)}</p><p className="text-xs text-bean-500">avg order</p></div>
          </div>
          {loyalty.perks.length > 0 && <p className="border-t border-cream-200 px-4 py-2.5 text-xs text-bean-700">Perks: {loyalty.perks.join(' · ')}</p>}
        </div>
      )}

      <div className="card p-4">
        <p className="label">Your taste</p>
        <div className="flex flex-wrap gap-1.5">
          {facts.length ? facts.map((f) => <span key={f} className="chip">{f}</span>) : <span className="text-sm text-bean-500">Not set</span>}
        </div>
      </div>

      <div className="card divide-y divide-cream-200">
        {[
          { to: '/onboarding', label: 'Edit taste & diet', icon: SlidersHorizontal },
          { to: '/orders', label: 'Order history', icon: Receipt },
          ...(isStaffRole(me?.role) ? [{ to: '/staff', label: 'Open staff console', icon: Store }] : []),
        ].map(({ to, label, icon: Icon }) => (
          <Link key={to} to={to} className="flex items-center gap-3 px-4 py-3.5 text-sm font-medium">
            <Icon className="h-4 w-4 text-bean-500" /> <span className="flex-1">{label}</span> <ChevronRight className="h-4 w-4 text-bean-300" />
          </Link>
        ))}
        <button onClick={signOut} className="flex w-full items-center gap-3 px-4 py-3.5 text-sm font-medium text-berry-600">
          <LogOut className="h-4 w-4" /> Sign out
        </button>
      </div>
    </div>
  );
}
