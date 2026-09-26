import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Navigate } from 'react-router-dom';
import { Mail, Trash2 } from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { ErrorNote, PageLoader } from '@/components/ui';

interface Team {
  members: { uid: string; email: string; displayName: string; role: string }[];
  invites: { email: string; role: string }[];
}

/** Managers invite employees by email; the role is granted when they next sign in. */
export default function TeamPage() {
  const { me } = useAuth();
  const [team, setTeam] = useState<Team | null>(null);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('staff');
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => api.get<Team>('/staff/team').then(setTeam).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);

  if (me?.role !== 'manager') return <Navigate to="/staff" replace />;

  async function invite(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    try {
      const r = await api.post<{ status: string; email: string }>('/staff/team/invites', { email, role });
      setMsg(r.status === 'granted' ? `${r.email} already had an account and is now ${role}.` : `Invited ${r.email}. They become ${role} when they sign in.`);
      setEmail('');
      load();
    } catch (e2) {
      setErr((e2 as Error).message);
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="mb-4 text-3xl">Team</h1>
      <form onSubmit={invite} className="card mb-5 flex flex-wrap gap-2 p-4">
        <label className="relative min-w-[220px] flex-1">
          <Mail className="absolute top-3 left-3 h-4 w-4 text-bean-300" />
          <input className="w-full pl-9" type="email" required placeholder="employee@email.com" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <select value={role} onChange={(e) => setRole(e.target.value)}><option value="staff">Staff</option><option value="manager">Manager</option></select>
        <button className="btn-primary">Invite</button>
        {msg && <p className="w-full text-sm text-leaf-600">{msg}</p>}
        <div className="w-full"><ErrorNote>{err}</ErrorNote></div>
      </form>
      {!team ? <PageLoader /> : (
        <div className="card divide-y divide-cream-200">
          {team.members.map((m) => (
            <div key={m.uid} className="flex items-center gap-3 px-4 py-3 text-sm">
              <div className="flex-1"><p className="font-medium">{m.displayName}</p><p className="text-xs text-bean-500">{m.email}</p></div>
              <span className="rounded-full bg-cream-200 px-2 py-0.5 text-xs font-semibold capitalize">{m.role}</span>
              {m.uid !== me.uid && <button className="text-bean-300 hover:text-berry-600" onClick={() => confirm(`Remove ${m.email}?`) && api.del(`/staff/team/${m.uid}`).then(load)} aria-label="Remove"><Trash2 className="h-4 w-4" /></button>}
            </div>
          ))}
          {team.invites.map((i) => (
            <div key={i.email} className="flex items-center gap-3 px-4 py-3 text-sm text-bean-500">
              <div className="flex-1">{i.email}</div>
              <span className="rounded-full border border-dashed border-cream-300 px-2 py-0.5 text-xs">Invited · {i.role}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
