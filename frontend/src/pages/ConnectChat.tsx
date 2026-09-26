import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { collection, orderBy, query } from 'firebase/firestore';
import { ArrowLeft, CalendarCheck, Clock, Flag, HeartHandshake, Send, ShieldOff } from 'lucide-react';
import { api } from '@/lib/api';
import { firestore } from '@/lib/firebase';
import { useAuth } from '@/context/AuthContext';
import { clock, countdown, toLocalInput } from '@/lib/format';
import { dateify, useDoc, useNow, useQuery } from '@/lib/hooks';
import type { Connection } from '@/lib/types';
import { ErrorNote, PageLoader, Sheet } from '@/components/ui';

interface Msg { id: string; senderUid: string; text: string; at: Date }

export default function ConnectChat() {
  const { id } = useParams();
  const { user } = useAuth();
  const uid = user!.uid;
  const nav = useNavigate();
  const { data: conn, error } = useDoc<Connection>(`connections/${id}`, dateify);
  const msgQ = useMemo(() => query(collection(firestore, `connections/${id}/messages`), orderBy('at')), [id]);
  const { data: messages } = useQuery<Msg>(msgQ, `msgs-${id}`, dateify);
  const now = useNow(15000);
  const [text, setText] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [meetOpen, setMeetOpen] = useState(false);
  const [safety, setSafety] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Braces matter: newer Chrome returns a Promise from scrollIntoView, and React
    // would treat a returned value as the effect's cleanup and crash on unmount.
    end.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  if (error) return <ErrorNote>{error}</ErrorNote>;
  if (!conn) return <PageLoader />;
  const otherUid = conn.members.find((m) => m !== uid)!;
  const other = conn.profiles[otherUid];
  const left = conn.windowEndsAt.getTime() - now;
  const open = conn.status === 'open' && left > 0;
  const canChat = open || conn.status === 'met';

  async function send(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setErr(null);
    const t = text;
    setText('');
    try {
      await api.post(`/connect/connections/${id}/messages`, { text: t });
    } catch (e2) {
      setErr((e2 as Error).message);
      setText(t);
    }
  }
  const meetup = (action: string, at?: string) => api.post(`/connect/connections/${id}/meetup`, { action, at }).catch((e2) => setErr(e2.message));

  const m = conn.meetup;
  const iConfirmed = m?.confirmedBy.includes(uid);
  const iMet = conn.metBy?.includes(uid);

  return (
    <div className="flex min-h-[70vh] flex-col">
      <div className="mb-3 flex items-center gap-3">
        <Link to="/connect" className="rounded-full p-1.5 hover:bg-cream-200" aria-label="Back"><ArrowLeft className="h-5 w-5" /></Link>
        <div className="flex-1">
          <p className="font-display text-xl leading-none">{other.firstName}</p>
          <p className="text-xs text-bean-500">{other.interests.slice(0, 3).join(' · ')}</p>
        </div>
        <button onClick={() => setSafety(true)} className="rounded-full p-1.5 text-bean-500 hover:bg-cream-200" aria-label="Safety"><Flag className="h-4 w-4" /></button>
      </div>

      <div className={`mb-3 flex items-center gap-2 rounded-xl px-3 py-2 text-sm ${conn.status === 'met' ? 'bg-leaf-100 text-leaf-600' : open ? 'bg-honey-100 text-bean-800' : 'bg-cream-200 text-bean-500'}`}>
        {conn.status === 'met' ? <><HeartHandshake className="h-4 w-4" /> You met! This connection is yours to keep.</> :
          open ? <><Clock className="h-4 w-4" /> <b>{countdown(left)}</b> left to meet up at {conn.cafeName.split('·').pop()?.trim()}</> :
          <>This 24-hour window has closed.</>}
      </div>

      {open && (
        <div className="card mb-3 p-3 text-sm">
          {!m ? (
            <button className="flex w-full items-center justify-center gap-2 font-medium text-ember-600" onClick={() => setMeetOpen(true)}><CalendarCheck className="h-4 w-4" /> Propose a time to meet</button>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <CalendarCheck className="h-4 w-4 text-ember-600" />
              <span className="flex-1">Meet at <b>{clock(m.at)}</b> {m.confirmedBy.length > 1 ? '· both confirmed' : `· proposed by ${m.proposedBy === uid ? 'you' : other.firstName}`}</span>
              {!iConfirmed && <button className="btn-primary px-3 py-1.5" onClick={() => meetup('accept')}>Confirm</button>}
              {m.confirmedBy.length > 1 && !iMet && <button className="btn-accent px-3 py-1.5" onClick={() => meetup('met')}>We met!</button>}
              {iMet && <span className="text-xs text-bean-500">Waiting for {other.firstName} to confirm</span>}
              <button className="text-xs text-bean-500 underline" onClick={() => setMeetOpen(true)}>Change</button>
            </div>
          )}
        </div>
      )}

      <div className="flex-1 space-y-2">
        {conn.icebreakers?.length > 0 && messages.length < 3 && (
          <div className="card p-3">
            <p className="label">Conversation starters</p>
            <div className="flex flex-col gap-1.5">
              {conn.icebreakers.map((i) => <button key={i} disabled={!canChat} onClick={() => setText(i)} className="rounded-lg bg-cream-200 px-3 py-2 text-left text-sm">{i}</button>)}
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.senderUid === uid ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] rounded-2xl px-3.5 py-2 text-sm ${msg.senderUid === uid ? 'rounded-br-md bg-bean-900 text-cream-50' : 'rounded-bl-md border border-cream-200 bg-cream-50'}`}>
              {msg.text}
              <p className={`mt-0.5 text-[10px] ${msg.senderUid === uid ? 'text-bean-300' : 'text-bean-500'}`}>{clock(msg.at)}</p>
            </div>
          </div>
        ))}
        <div ref={end} />
      </div>

      <ErrorNote>{err}</ErrorNote>
      {canChat ? (
        <form onSubmit={send} className="sticky bottom-[84px] mt-3 flex gap-2 rounded-2xl border border-cream-300 bg-white p-1.5 shadow-sm">
          <input className="flex-1 border-0 focus:ring-0" placeholder="Message…" value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} />
          <button className="btn-accent px-3" disabled={!text.trim()} aria-label="Send"><Send className="h-4 w-4" /></button>
        </form>
      ) : (
        <p className="mt-3 text-center text-sm text-bean-500">Messages are read-only now and will be deleted in 7 days.</p>
      )}

      <MeetSheet open={meetOpen} onClose={() => setMeetOpen(false)} max={conn.windowEndsAt} onPick={(at) => { meetup('propose', at); setMeetOpen(false); }} />
      <Sheet open={safety} onClose={() => setSafety(false)} title="Safety">
        <div className="space-y-2">
          <button className="btn-ghost w-full" onClick={async () => { await api.post(`/connect/connections/${id}/close`); setSafety(false); }}>Close this connection</button>
          <button className="btn-ghost w-full text-berry-600" onClick={async () => { await api.post('/connect/report', { uid: otherUid, reason: 'Reported from chat', context: id }); setSafety(false); }}><Flag className="h-4 w-4" /> Report</button>
          <button className="btn-primary w-full bg-berry-600 hover:bg-berry-600" onClick={async () => { await api.post('/connect/block', { uid: otherUid }); nav('/connect'); }}><ShieldOff className="h-4 w-4" /> Block {other.firstName}</button>
        </div>
      </Sheet>
    </div>
  );
}

function MeetSheet({ open, onClose, max, onPick }: { open: boolean; onClose: () => void; max: Date; onPick: (iso: string) => void }) {
  const [v, setV] = useState(toLocalInput(new Date(Date.now() + 3600000)));
  return (
    <Sheet open={open} onClose={onClose} title="When should you meet?">
      <p className="-mt-2 mb-3 text-sm text-bean-500">Pick a time before {clock(max)} tomorrow-ish. Meet at the café, a public place.</p>
      <input type="datetime-local" className="w-full" value={v} min={toLocalInput(new Date())} max={toLocalInput(max)} onChange={(e) => setV(e.target.value)} />
      <button className="btn-accent mt-3 w-full" onClick={() => onPick(new Date(v).toISOString())}>Propose</button>
    </Sheet>
  );
}
