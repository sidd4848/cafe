import { useEffect, useState } from 'react';
import { Minus, Plus } from 'lucide-react';
import { useSession } from '@/context/SessionContext';
import { rupees } from '@/lib/format';
import type { MenuItem } from '@/lib/types';
import { ErrorNote, Sheet, Spinner } from './ui';

/** Customise an item (size, milk, ...) and add it to the cart. */
export function ItemSheet({ item, onClose, preset }: { item: MenuItem | null; onClose: () => void; preset?: Record<string, string> }) {
  const { menu, addItem } = useSession();
  const [mods, setMods] = useState<Record<string, string>>({});
  const [qty, setQty] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!item || !menu) return;
    const init: Record<string, string> = {};
    for (const g of item.modifiers) init[g] = preset?.[g] ?? menu.modifiers[g].options[0].id;
    setMods(init);
    setQty(1);
    setError(null);
  }, [item, menu, preset]);

  if (!item || !menu) return null;
  const unit = item.price + item.modifiers.reduce((sum, g) => sum + (menu.modifiers[g].options.find((o) => o.id === mods[g])?.delta ?? 0), 0);

  async function add() {
    setBusy(true);
    try {
      await addItem(item!.id, mods, qty);
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open={!!item} onClose={onClose} title={item.name}>
      <p className="-mt-2 mb-4 text-sm text-bean-500">{item.description}</p>
      <div className="space-y-4">
        {item.modifiers.map((g) => (
          <div key={g}>
            <p className="label">{menu.modifiers[g].label}</p>
            <div className="flex flex-wrap gap-2">
              {menu.modifiers[g].options.map((o) => (
                <button key={o.id} onClick={() => setMods({ ...mods, [g]: o.id })} className={`chip py-1.5 ${mods[g] === o.id ? 'chip-on' : ''}`}>
                  {o.label}
                  {o.delta ? <span className="opacity-70">+{rupees(o.delta)}</span> : null}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      <ErrorNote>{error}</ErrorNote>
      <div className="mt-6 flex items-center gap-3">
        <div className="flex items-center rounded-xl border border-cream-300 bg-white">
          <button className="p-2.5" onClick={() => setQty(Math.max(1, qty - 1))} aria-label="Less"><Minus className="h-4 w-4" /></button>
          <span className="w-6 text-center font-semibold">{qty}</span>
          <button className="p-2.5" onClick={() => setQty(Math.min(10, qty + 1))} aria-label="More"><Plus className="h-4 w-4" /></button>
        </div>
        <button className="btn-accent flex-1" onClick={add} disabled={busy}>
          {busy && <Spinner className="h-4 w-4 text-white" />} Add · {rupees(unit * qty)}
        </button>
      </div>
    </Sheet>
  );
}
