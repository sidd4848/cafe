import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { collection, limit, orderBy, query, where } from 'firebase/firestore';
import { Clock, Heart, LogOut, QrCode, Send, Shield, Sparkles, UserPlus, X } from 'lucide-react';
import { api } from '@/lib/api';
import { firestore } from '@/lib/firebase';
import { useAuth } from '@/context/AuthContext';
import { useSession } from '@/context/SessionContext';
import { countdown } from '@/lib/format';
import { dateify, useNow, useQuery } from '@/lib/hooks';
import type { Connection, Person, PublicProfile, Spark } from '@/lib/types';
import { Empty, ErrorNote, PageLoader, Sheet, Spinner } from '@/components/ui';

interface ProfileRes {
  profile: (PublicProfile & { visible: boolean; ageConfirmed18: boolean }) | null;
  presence: { cafeId?: string; expiresAt?: string; mood?: string };
}

export default function Connect() {
  const { user } = useAuth();
  const { cafeId } = useSession();
  const uid = user!.uid;
  const [state, setState] = useState<ProfileRes | null>(null);
  const [editing, setEditing] = useState(false);
  const now = useNow(30000);

  const load = useCallback(() => api.get<ProfileRes>('/connect/profile').then(setState), []);
  useEffect(() => {
    load();
  }, [load]);

  const incomingQ = useMemo(() => query(collection(firestore, 'sparks'), where('toUid', '==', uid), where('status', '==', 'pending'), orderBy('createdAt', 'desc')), [uid]);
  const outgoingQ = useMemo(() => query(collection(firestore, 'sparks'), where('fromUid', '==', uid), orderBy('createdAt', 'desc'), limit(10)), [uid]);
  const connQ = useMemo(() => query(collection(firestore, 'connections'), where('members', 'array-contains', uid), orderBy('openedAt', 'desc'), limit(20)), [uid]);
  const incoming = useQuery<Spark>(incomingQ, `in-${uid}`, dateify).data.filter((s) => s.expiresAt.getTime() > now);
  const outgoing = useQuery<Spark>(outgoingQ, `out-${uid}`, dateify).data;
  const connections = useQuery<Connection>(connQ, `conn-${uid}`, dateify).data;

  if (!state) return <PageLoader />;
  const checkedIn = state.presence.cafeId === cafeId;

  if (!state.profile || editing) {
    return <ProfileEditor initial={state.profile} onDone={() => { setEditing(false); load(); }} onCancel={state.profile ? () => setEditing(false) : undefined} />;
  }

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-3xl">Connect</h1>
          <p className="text-sm text-bean-500">Meet someone at the café. Every connection gets 24 hours.</p>
        </div>
        <button className="text-sm font-medium text-ember-600" onClick={() => setEditing(true)}>Edit profile</button>
      </div>

      {!state.profile.visible && (
        <div className="rounded-xl bg-honey-100 px-3 py-2 text-sm">You're hidden. <button className="font-semibold underline" onClick={() => setEditing(true)}>Turn on visibility</button> to meet people.</div>
      )}

      {incoming.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-lg">Sparks for you</h2>
          {incoming.map((s) => <IncomingSpark key={s.id} spark={s} now={now} />)}
        </section>
      )}

      {connections.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-lg">Your connections</h2>
          {connections.map((c) => {
            const other = c.profiles[c.members.find((m) => m !== uid)!];
            const left = c.windowEndsAt.getTime() - now;
            return (
              <Link key={c.id} to={`/connect/c/${c.id}`} className="card flex items-center gap-3 p-3.5">
                <div className="grid h-10 w-10 place-items-center rounded-full bg-ember-100 font-display text-lg text-ember-600">{other?.firstName?.[0]}</div>
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{other?.firstName}</p>
                  <p className="truncate text-xs text-bean-500">{c.lastMessage ?? c.icebreakers?.[0]}</p>
                </div>
                {c.status === 'open' ? (
                  <span className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${left < 3 * 3600000 ? 'bg-berry-100 text-berry-600' : 'bg-honey-100 text-bean-800'}`}><Clock className="h-3 w-3" />{countdown(left)}</span>
                ) : (
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${c.status === 'met' ? 'bg-leaf-100 text-leaf-600' : 'bg-cream-200 text-bean-500'}`}>{c.status === 'met' ? 'Met ✓' : c.status}</span>
                )}
              </Link>
            );
          })}
        </section>
      )}

      {checkedIn ? (
        <HereNow cafeId={cafeId} presence={state.presence} outgoing={outgoing} onCheckout={load} />
      ) : (
        <div className="card p-5 text-center">
          <QrCode className="mx-auto h-10 w-10 text-bean-500" />
          <p className="mt-2 font-display text-xl">Scan the QR on your table</p>
          <p className="mt-1 text-sm text-bean-500">Check in to see who's here and open to a chat. Only people checked in at this café can see you, and only while you're here.</p>
        </div>
      )}

      <p className="flex items-start gap-2 text-xs text-bean-500"><Shield className="mt-0.5 h-3.5 w-3.5 shrink-0" /> First names only. No exact location. Messages are moderated, and you can block or report anyone.</p>
    </div>
  );
}

function IncomingSpark({ spark, now }: { spark: Spark; now: number }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const act = async (a: 'accept' | 'decline') => {
    setBusy(true);
    try {
      await api.post(`/connect/sparks/${spark.id}/${a}`);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="card rise border-ember-500/40 p-4">
      <div className="flex items-center justify-between">
        <p className="font-medium"><Sparkles className="mr-1 inline h-4 w-4 text-ember-500" />{spark.from.firstName}</p>
        <span className="text-xs text-bean-500">expires in {countdown(spark.expiresAt.getTime() - now)}</span>
      </div>
      <p className="mt-2 rounded-xl bg-cream-200 px-3 py-2 text-sm">"{spark.note}"</p>
      {spark.sharedInterests.length > 0 && <p className="mt-2 text-xs text-bean-500">You both like {spark.sharedInterests.join(', ')}</p>}
      <ErrorNote>{err}</ErrorNote>
      <div className="mt-3 flex gap-2">
        <button className="btn-accent flex-1 py-2" disabled={busy} onClick={() => act('accept')}><Heart className="h-4 w-4" /> Accept · 24h chat</button>
        <button className="btn-ghost px-3 py-2" disabled={busy} onClick={() => act('decline')}><X className="h-4 w-4" /></button>
      </div>
    </div>
  );
}

function HereNow({ cafeId, presence, outgoing, onCheckout }: { cafeId: string; presence: ProfileRes['presence']; outgoing: Spark[]; onCheckout: () => void }) {
  const [people, setPeople] = useState<Person[] | null>(null);
  const [target, setTarget] = useState<Person | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => api.get<Person[]>(`/connect/cafes/${cafeId}/people`).then(setPeople).catch((e) => setErr(e.message)), [cafeId]);
  useEffect(() => {
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, [load]);

  const pendingTo = new Set(outgoing.filter((s) => s.status === 'pending').map((s) => s.toUid));
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-lg">Here now</h2>
        <button className="flex items-center gap-1 text-xs text-bean-500" onClick={async () => { await api.post('/connect/checkout', { cafeId }); onCheckout(); }}>
          <LogOut className="h-3.5 w-3.5" /> Check out{presence.expiresAt ? ` (auto at ${new Date(presence.expiresAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })})` : ''}
        </button>
      </div>
      <ErrorNote>{err}</ErrorNote>
      {!people ? <PageLoader /> : people.length === 0 ? (
        <Empty icon={<UserPlus className="h-5 w-5" />} title="Nobody else has checked in yet">We'll refresh this every few seconds.</Empty>
      ) : (
        <div className="grid grid-cols-1 gap-2.5">
          {people.map((p) => (
            <div key={p.uid} className="card min-w-0 p-4">
              <div className="flex min-w-0 items-center gap-3">
                <div className="grid h-10 w-10 place-items-center rounded-full bg-cream-200 font-display text-lg">{p.firstName[0]}</div>
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{p.firstName} {p.mood && <span className="text-xs font-normal text-bean-500">· {p.mood}</span>}</p>
                  <p className="truncate text-xs text-bean-500">{p.bio}</p>
                </div>
                <button className="btn-accent shrink-0 px-3 py-2" disabled={pendingTo.has(p.uid)} onClick={() => setTarget(p)}>
                  {pendingTo.has(p.uid) ? 'Sent' : <><Sparkles className="h-4 w-4" /> Spark</>}
                </button>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {p.interests.map((i) => <span key={i} className={`chip py-0.5 ${p.sharedInterests.includes(i) ? 'border-ember-500 bg-ember-100 text-ember-600' : ''}`}>{i}</span>)}
              </div>
            </div>
          ))}
        </div>
      )}
      <SparkSheet cafeId={cafeId} person={target} onClose={() => setTarget(null)} />
    </section>
  );
}

function SparkSheet({ cafeId, person, onClose }: { cafeId: string; person: Person | null; onClose: () => void }) {
  const [ideas, setIdeas] = useState<string[] | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!person) return;
    setIdeas(null);
    setNote('');
    setErr(null);
    api.get<{ suggestions: string[] }>(`/connect/sparks/draft?toUid=${person.uid}&cafeId=${cafeId}`)
      .then((r) => { setIdeas(r.suggestions); setNote(r.suggestions[0] ?? ''); })
      .catch(() => setIdeas([]));
  }, [person, cafeId]);

  async function send() {
    setBusy(true);
    setErr(null);
    try {
      await api.post('/connect/sparks', { toUid: person!.uid, cafeId, note });
      onClose();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open={!!person} onClose={onClose} title={`Spark ${person?.firstName ?? ''}`}>
      <p className="-mt-2 mb-3 text-sm text-bean-500">If they accept, you'll both get 24 hours to chat and meet up here.</p>
      <p className="label">AI icebreakers</p>
      {!ideas ? <div className="py-3"><Spinner /></div> : (
        <div className="mb-3 space-y-2">
          {ideas.map((i) => (
            <button key={i} onClick={() => setNote(i)} className={`card w-full px-3 py-2 text-left text-sm ${note === i ? 'border-bean-900 ring-1 ring-bean-900' : ''}`}>{i}</button>
          ))}
        </div>
      )}
      <textarea className="w-full" rows={3} maxLength={280} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Say hi…" />
      <ErrorNote>{err}</ErrorNote>
      <button className="btn-accent mt-3 w-full" disabled={!note.trim() || busy} onClick={send}>{busy ? <Spinner className="h-4 w-4 text-white" /> : <Send className="h-4 w-4" />} Send spark</button>
    </Sheet>
  );
}

function ProfileEditor({ initial, onDone, onCancel }: { initial: ProfileRes['profile']; onDone: () => void; onCancel?: () => void }) {
  const { me } = useAuth();
  const [opts, setOpts] = useState<{ interests: string[]; openTo: string[] } | null>(null);
  const [form, setForm] = useState({
    firstName: initial?.firstName ?? me?.displayName?.split(' ')[0] ?? '',
    bio: initial?.bio ?? '',
    interests: initial?.interests ?? [],
    openTo: initial?.openTo ?? ['chat'],
    visible: initial?.visible ?? true,
    ageConfirmed18: initial?.ageConfirmed18 ?? false,
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api.get<{ interests: string[]; openTo: string[] }>('/connect/options').then(setOpts);
  }, []);

  const toggle = (key: 'interests' | 'openTo', v: string, max = 8) => {
    const arr = form[key];
    setForm({ ...form, [key]: arr.includes(v) ? arr.filter((x) => x !== v) : arr.length < max ? [...arr, v] : arr });
  };

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      await api.put('/connect/profile', form);
      onDone();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!opts) return <PageLoader />;
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-3xl">Your Connect profile</h1>
        <p className="text-sm text-bean-500">Only people checked in at the same café see this.</p>
      </div>
      <div><p className="label">First name</p><input className="w-full" value={form.firstName} onChange={(e) => setForm({ ...form, firstName: e.target.value })} maxLength={24} /></div>
      <div><p className="label">One-line bio</p><input className="w-full" value={form.bio} onChange={(e) => setForm({ ...form, bio: e.target.value })} maxLength={140} placeholder="Product designer, always on my 3rd cortado" /></div>
      <div>
        <p className="label">Interests (up to 8)</p>
        <div className="flex flex-wrap gap-1.5">{opts.interests.map((i) => <button key={i} onClick={() => toggle('interests', i)} className={`chip ${form.interests.includes(i) ? 'chip-on' : ''}`}>{i}</button>)}</div>
      </div>
      <div>
        <p className="label">Open to</p>
        <div className="flex flex-wrap gap-1.5">{opts.openTo.map((i) => <button key={i} onClick={() => toggle('openTo', i)} className={`chip ${form.openTo.includes(i) ? 'chip-on' : ''}`}>{i.replace('_', ' ')}</button>)}</div>
      </div>
      <label className="card flex items-center gap-3 p-3.5 text-sm">
        <input type="checkbox" className="h-4 w-4" checked={form.visible} onChange={(e) => setForm({ ...form, visible: e.target.checked })} />
        <span>Visible to others when I check in</span>
      </label>
      <label className="card flex items-center gap-3 p-3.5 text-sm">
        <input type="checkbox" className="h-4 w-4" checked={form.ageConfirmed18} onChange={(e) => setForm({ ...form, ageConfirmed18: e.target.checked })} />
        <span>I'm 18 or older</span>
      </label>
      <ErrorNote>{err}</ErrorNote>
      <div className="flex gap-2">
        {onCancel && <button className="btn-ghost" onClick={onCancel}>Cancel</button>}
        <button className="btn-accent flex-1" onClick={save} disabled={busy || !form.firstName}>{busy && <Spinner className="h-4 w-4 text-white" />} Save</button>
      </div>
    </div>
  );
}
