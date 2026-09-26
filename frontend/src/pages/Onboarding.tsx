import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import type { Prefs } from '@/lib/types';
import { ErrorNote, Spinner } from '@/components/ui';

type Opt<T> = { v: T; label: string; hint?: string };

const STEPS: { key: keyof Prefs; title: string; multi?: boolean; options: Opt<string | number>[] }[] = [
  { key: 'temperature', title: 'Hot or iced?', options: [{ v: 'hot', label: '☕ Hot' }, { v: 'iced', label: '🧊 Iced' }, { v: 'any', label: 'Depends on the day' }] },
  { key: 'caffeine', title: 'How strong do you like it?', options: [{ v: 'strong', label: 'Strong & bold' }, { v: 'regular', label: 'Regular' }, { v: 'light', label: 'Light' }, { v: 'none', label: 'No caffeine' }] },
  { key: 'milk', title: 'Your milk', options: [{ v: 'dairy', label: 'Whole milk' }, { v: 'oat', label: 'Oat' }, { v: 'almond', label: 'Almond' }, { v: 'soy', label: 'Soy' }, { v: 'none', label: 'Black, please' }] },
  { key: 'sweetness', title: 'Sweet tooth?', options: [{ v: 0, label: 'No sugar' }, { v: 1, label: 'A little' }, { v: 2, label: 'Sweet' }, { v: 3, label: 'Dessert in a cup' }] },
  { key: 'flavours', title: 'Flavours you love', multi: true, options: ['chocolate', 'fruity', 'nutty', 'spiced', 'caramel', 'earthy', 'citrus', 'creamy'].map((f) => ({ v: f, label: f[0].toUpperCase() + f.slice(1) })) },
  { key: 'diet', title: 'Any diet?', options: [{ v: 'any', label: 'I eat everything' }, { v: 'veg', label: 'Vegetarian' }, { v: 'vegan', label: 'Vegan' }] },
  { key: 'avoid', title: 'Anything to avoid?', multi: true, options: [{ v: 'nuts', label: 'Nuts' }, { v: 'gluten', label: 'Gluten' }, { v: 'egg', label: 'Egg' }, { v: 'dairy', label: 'Dairy' }] },
];

export default function Onboarding() {
  const { me, refreshMe } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [step, setStep] = useState(0);
  const [prefs, setPrefs] = useState<Prefs>({ flavours: [], avoid: [], diet: 'any', ...(me?.prefs ?? {}) });
  const [name, setName] = useState(me?.displayName ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const s = STEPS[step];
  const value = prefs[s.key] as unknown;
  const toggle = (v: string | number) => {
    if (s.multi) {
      const arr = (value as string[]) ?? [];
      setPrefs({ ...prefs, [s.key]: arr.includes(v as string) ? arr.filter((x) => x !== v) : [...arr, v] });
    } else {
      setPrefs({ ...prefs, [s.key]: v });
      if (step < STEPS.length - 1) setTimeout(() => setStep(step + 1), 180);
    }
  };

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.put('/me/prefs', { ...prefs, displayName: name });
      await refreshMe();
      nav(params.get('next') || '/', { replace: true });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const last = step === STEPS.length - 1;
  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col px-5 py-8">
      <div className="mb-8 flex gap-1.5">
        {STEPS.map((_, i) => (
          <div key={i} className={`h-1 flex-1 rounded-full ${i <= step ? 'bg-ember-500' : 'bg-cream-300'}`} />
        ))}
      </div>
      {step === 0 && (
        <div className="mb-6">
          <p className="label">What should we call you?</p>
          <input className="w-full" value={name} onChange={(e) => setName(e.target.value)} placeholder="First name" />
        </div>
      )}
      <p className="text-sm text-bean-500">Tell us your taste · {step + 1}/{STEPS.length}</p>
      <h1 className="mt-1 mb-6 text-3xl">{s.title}</h1>
      <div className="rise grid gap-2.5" key={step}>
        {s.options.map((o) => {
          const on = s.multi ? ((value as (string | number)[]) ?? []).includes(o.v) : value === o.v;
          return (
            <button key={String(o.v)} onClick={() => toggle(o.v)} className={`card px-4 py-3.5 text-left font-medium transition ${on ? 'border-bean-900 bg-bean-900 text-cream-50' : 'hover:border-bean-300'}`}>
              {o.label}
            </button>
          );
        })}
      </div>
      <div className="mt-auto pt-8">
        <ErrorNote>{error}</ErrorNote>
        <div className="mt-3 flex gap-3">
          {step > 0 && (
            <button className="btn-ghost" onClick={() => setStep(step - 1)}>
              <ArrowLeft className="h-4 w-4" />
            </button>
          )}
          {last ? (
            <button className="btn-accent flex-1" onClick={save} disabled={busy}>
              {busy && <Spinner className="h-4 w-4 text-white" />} Start ordering
            </button>
          ) : (
            <button className="btn-primary flex-1" onClick={() => setStep(step + 1)}>
              {s.multi ? 'Next' : 'Skip'} <ArrowRight className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
