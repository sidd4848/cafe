import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { CalendarClock, Check, Filter, MessageCircle, Search, Send, UtensilsCrossed, X } from 'lucide-react';
import { useSession } from '@/context/SessionContext';
import { api } from '@/lib/api';
import { dayClock, rupees } from '@/lib/format';
import type { MenuItem } from '@/lib/types';
import { ItemSheet } from '@/components/ItemSheet';
import { ErrorNote, PageLoader, Spinner } from '@/components/ui';

const STARTERS = [
  'Something iced and not too sweet',
  'My usual please',
  "I'm vegan. What do you recommend?",
  "A latte with oat milk, I'll be there in 15 min",
];

interface FilterResult {
  summary: string;
  itemIds: string[];
  excluded: { id: string; reason: string }[];
}

export default function Order() {
  const [tab, setTab] = useState<'chat' | 'menu'>('chat');
  return (
    <div>
      <div className="mb-4 grid grid-cols-2 rounded-xl bg-cream-200 p-1 text-sm font-medium">
        {(['chat', 'menu'] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`flex items-center justify-center gap-1.5 rounded-lg py-2 ${tab === t ? 'bg-cream-50 shadow-sm' : 'text-bean-500'}`}>
            {t === 'chat' ? <MessageCircle className="h-4 w-4" /> : <UtensilsCrossed className="h-4 w-4" />}
            {t === 'chat' ? 'Chat with barista' : 'Menu'}
          </button>
        ))}
      </div>
      {tab === 'chat' ? <Chat /> : <MenuView />}
    </div>
  );
}

function PickupNote() {
  const { session, setPickup } = useSession();
  if (!session?.pickupAt) return null;
  return (
    <div className="mb-3 flex items-center gap-2 rounded-xl bg-honey-100 px-3 py-2 text-sm">
      <CalendarClock className="h-4 w-4" /> Pre-order for <b>{dayClock(session.pickupAt)}</b>
      <button className="ml-auto text-bean-500" onClick={() => setPickup(null)} aria-label="Clear pickup time"><X className="h-4 w-4" /></button>
    </div>
  );
}

function Chat() {
  const { session, chat, busy } = useSession();
  const [text, setText] = useState('');
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Braces matter: newer Chrome returns a Promise from scrollIntoView, and React
    // would treat a returned value as the effect's cleanup and crash on unmount.
    end.current?.scrollIntoView({ behavior: 'smooth' });
  }, [session?.messages.length, busy]);
  if (!session) return <PageLoader />;

  const send = (t: string) => {
    if (!t.trim() || busy) return;
    setText('');
    chat(t.trim());
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    send(text);
  };

  return (
    <div className="flex min-h-[60vh] flex-col">
      <PickupNote />
      <div className="flex-1 space-y-3">
        {session.messages.length === 0 && (
          <div className="rise card p-4">
            <p className="font-display text-lg">Hi! What can I get you?</p>
            <p className="mt-1 text-sm text-bean-500">Tell me what you're in the mood for. I know the menu, your preferences, and how busy the bar is.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {STARTERS.map((s) => (
                <button key={s} className="chip" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {session.messages.map((m, i) => (
          <div key={i} className={`rise flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm ${m.role === 'user' ? 'rounded-br-md bg-bean-900 text-cream-50' : 'rounded-bl-md border border-cream-200 bg-cream-50'}`}>
              <p className="whitespace-pre-wrap">{m.text}</p>
              {m.actions && m.actions.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {m.actions.map((a, j) => (
                    <span key={j} className="inline-flex items-center gap-1 rounded-full bg-leaf-100 px-2 py-0.5 text-[11px] font-medium text-leaf-600"><Check className="h-3 w-3" />{a}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <div className="rise flex justify-start" aria-live="polite">
            <div className="flex items-center gap-2 rounded-2xl rounded-bl-md border border-cream-200 bg-cream-50 px-3.5 py-3">
              <span className="flex gap-1">
                {[0, 1, 2].map((i) => <span key={i} className="typing-dot h-1.5 w-1.5 rounded-full bg-bean-500" style={{ animationDelay: `${i * 0.2}s` }} />)}
              </span>
              <span className="text-xs text-bean-500">Barista is on it…</span>
            </div>
          </div>
        )}
        <div ref={end} />
      </div>
      <form onSubmit={onSubmit} className="sticky bottom-[132px] mt-4 flex gap-2 rounded-2xl border border-cream-300 bg-white p-1.5 shadow-sm">
        <input className="flex-1 border-0 focus:ring-0" placeholder={busy ? 'Waiting for the barista…' : 'Ask for anything on the menu…'} value={text} onChange={(e) => setText(e.target.value)} maxLength={500} />
        <button className="btn-accent px-3" disabled={!text.trim() || busy} aria-label="Send">{busy ? <Spinner className="h-4 w-4 text-white" /> : <Send className="h-4 w-4" />}</button>
      </form>
    </div>
  );
}

function MenuView() {
  const { menu, cafeId } = useSession();
  const [cat, setCat] = useState<string>('all');
  const [q, setQ] = useState('');
  const [pick, setPick] = useState<MenuItem | null>(null);
  const [needs, setNeeds] = useState('');
  const [filter, setFilter] = useState<FilterResult | null>(null);
  const [filtering, setFiltering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const items = useMemo(() => {
    if (!menu) return [];
    const allowed = filter ? new Set(filter.itemIds) : null;
    return menu.items.filter((i) => (cat === 'all' || i.category === cat)
      && (!q || `${i.name} ${i.tags.join(' ')}`.toLowerCase().includes(q.toLowerCase()))
      && (!allowed || allowed.has(i.id)));
  }, [menu, cat, q, filter]);

  async function applyNeeds(e: FormEvent) {
    e.preventDefault();
    if (!needs.trim()) return;
    setFiltering(true);
    setError(null);
    try {
      setFilter(await api.post<FilterResult>(`/cafes/${cafeId}/menu/filter`, { query: needs }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setFiltering(false);
    }
  }

  if (!menu) return <PageLoader />;
  return (
    <div>
      <PickupNote />
      <form onSubmit={applyNeeds} className="card mb-3 p-3">
        <p className="label flex items-center gap-1"><Filter className="h-3 w-3" /> Dietary needs</p>
        <div className="flex gap-2">
          <input className="flex-1" value={needs} onChange={(e) => setNeeds(e.target.value)} placeholder='e.g. "gluten-free, high-protein, no nuts"' />
          <button className="btn-primary px-3" disabled={filtering}>{filtering ? <Spinner className="h-4 w-4 text-white" /> : 'Apply'}</button>
        </div>
        <ErrorNote>{error}</ErrorNote>
        {filter && (
          <div className="mt-2 flex items-start gap-2 text-xs text-bean-700">
            <p className="flex-1">{filter.summary} · <b>{filter.itemIds.length}</b> items match, {filter.excluded.length} hidden.</p>
            <button className="text-ember-600" onClick={() => { setFilter(null); setNeeds(''); }}>Clear</button>
          </div>
        )}
      </form>
      <label className="relative mb-3 block">
        <Search className="absolute top-3 left-3 h-4 w-4 text-bean-300" />
        <input className="w-full pl-9" placeholder="Search the menu" value={q} onChange={(e) => setQ(e.target.value)} />
      </label>
      <div className="-mx-4 mb-4 flex gap-2 overflow-x-auto px-4 scroll-thin">
        {[{ id: 'all', label: 'All' }, ...menu.categories].map((c) => (
          <button key={c.id} onClick={() => setCat(c.id)} className={`chip shrink-0 ${cat === c.id ? 'chip-on' : ''}`}>{c.label}</button>
        ))}
      </div>
      <div className="grid gap-2.5">
        {items.map((i) => (
          <button key={i.id} onClick={() => setPick(i)} className="card flex items-start gap-3 p-3.5 text-left">
            <div className="min-w-0 flex-1">
              <p className="font-medium">{i.name}</p>
              <p className="mt-0.5 line-clamp-2 text-xs text-bean-500">{i.description}</p>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {i.dietary.includes('vegan') && <span className="rounded bg-leaf-100 px-1.5 text-[10px] font-semibold text-leaf-600">VEGAN</span>}
                {i.dietary.includes('non_veg') ? <span className="rounded bg-berry-100 px-1.5 text-[10px] font-semibold text-berry-600">NON-VEG</span> : <span className="rounded bg-leaf-100 px-1.5 text-[10px] font-semibold text-leaf-600">VEG</span>}
                {i.tags.includes('iced') && <span className="rounded bg-cream-200 px-1.5 text-[10px] font-semibold text-bean-700">ICED</span>}
              </div>
            </div>
            <span className="text-sm font-semibold">{rupees(i.price)}</span>
          </button>
        ))}
        {items.length === 0 && <p className="py-8 text-center text-sm text-bean-500">Nothing matches. <Link to="/order" onClick={() => setFilter(null)} className="text-ember-600">Clear filters</Link></p>}
      </div>
      <ItemSheet item={pick} onClose={() => setPick(null)} />
    </div>
  );
}
