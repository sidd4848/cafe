import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { config } from '@/lib/config';
import { minutes, rupees } from '@/lib/format';
import type { Menu, MenuItem } from '@/lib/types';
import { ErrorNote, PageLoader } from '@/components/ui';

/** 86 an item (hide it from guests and the AI) and see learned prep times. */
export default function MenuAdmin() {
  const cafeId = config.cafeId;
  const [menu, setMenu] = useState<Menu | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => api.get<Menu>(`/cafes/${cafeId}/menu`).then(setMenu), [cafeId]);
  useEffect(() => { load(); }, [load]);

  const toggle = async (i: MenuItem) => {
    setErr(null);
    try {
      await api.patch(`/staff/cafes/${cafeId}/menu/${i.id}`, { available: !i.available });
      setMenu((m) => m && { ...m, items: m.items.map((x) => (x.id === i.id ? { ...x, available: !x.available } : x)) });
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  if (!menu) return <PageLoader />;
  return (
    <div>
      <h1 className="mb-1 text-3xl">Menu</h1>
      <p className="mb-4 text-sm text-bean-500">Turn items off when you run out. Prep times are learned from the order board.</p>
      <ErrorNote>{err}</ErrorNote>
      {menu.categories.map((c) => (
        <section key={c.id} className="mb-5">
          <h2 className="mb-2 font-sans text-xs font-semibold tracking-wider text-bean-500 uppercase">{c.label}</h2>
          <div className="card divide-y divide-cream-200">
            {menu.items.filter((i) => i.category === c.id).map((i) => (
              <div key={i.id} className={`flex items-center gap-3 px-4 py-2.5 ${i.available ? '' : 'opacity-50'}`}>
                <span className="flex-1 text-sm font-medium">{i.name}</span>
                <span className="w-20 text-right text-xs text-bean-500">prep {minutes(i.prepSec)}</span>
                <span className="w-14 text-right text-sm">{rupees(i.price)}</span>
                <button onClick={() => toggle(i)} role="switch" aria-checked={i.available} aria-label={`${i.name} available`}
                  className={`relative h-6 w-11 rounded-full transition ${i.available ? 'bg-leaf-600' : 'bg-cream-300'}`}>
                  <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${i.available ? 'left-5.5' : 'left-0.5'}`} />
                </button>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
