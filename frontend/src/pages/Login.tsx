import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { BadgeCheck, Coffee, Lock, Mail, Sparkles, Timer, User as UserIcon } from 'lucide-react';
import { friendlyAuthError, isStaffRole, useAuth } from '@/context/AuthContext';
import { ErrorNote, Spinner } from '@/components/ui';

function GoogleMark() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.76h3.57c2.08-1.92 3.28-4.74 3.28-8.09Z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.76c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z" />
      <path fill="#FBBC05" d="M5.84 14.11a6.6 6.6 0 0 1 0-4.22V7.05H2.18a11 11 0 0 0 0 9.9l3.66-2.84Z" />
      <path fill="#EA4335" d="M12 4.75c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 1.46 14.97.5 12 .5A11 11 0 0 0 2.18 7.05l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53Z" />
    </svg>
  );
}

/**
 * One screen, two doors. Customers can register; employees sign in with the account a
 * manager invited, and are turned away here if that account has no staff role.
 */
export default function Login({ audience }: { audience: 'customer' | 'staff' }) {
  const staff = audience === 'staff';
  const { user, me, loading, signInWithGoogle, signInWithEmail, registerWithEmail, signOut, refreshMe } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const next = params.get('next') || '/';
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState<'email' | 'google' | null>(null);
  const [error, setError] = useState<string | null>(params.get('denied') ? 'That account is not an employee account. Ask your manager for an invite.' : null);

  // Already signed in: send them where they belong.
  useEffect(() => {
    if (loading || !user || !me || busy) return;
    if (staff) {
      if (isStaffRole(me.role)) nav('/staff', { replace: true });
    } else {
      nav(next, { replace: true });
    }
  }, [loading, user, me, staff, nav, next, busy]);

  async function finish() {
    const m = await refreshMe();
    if (staff) {
      if (m && isStaffRole(m.role)) nav('/staff', { replace: true });
      else {
        await signOut();
        setError('That account is not an employee account. Ask your manager for an invite.');
      }
    } else nav(next, { replace: true });
  }

  async function run(kind: 'email' | 'google', fn: () => Promise<void>) {
    setError(null);
    setBusy(kind);
    try {
      await fn();
      await finish();
    } catch (e) {
      setError(friendlyAuthError(e));
    } finally {
      setBusy(null);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    run('email', () => (mode === 'signin' || staff ? signInWithEmail(email, password) : registerWithEmail(name, email, password)));
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className={`relative hidden overflow-hidden p-12 lg:flex lg:flex-col lg:justify-between ${staff ? 'bg-bean-950' : 'bg-bean-900'} text-cream-50`}>
        <div className="pointer-events-none absolute inset-0 opacity-50" style={{ backgroundImage: 'radial-gradient(circle at 15% 20%, rgba(217,121,74,0.35), transparent 45%), radial-gradient(circle at 85% 85%, rgba(217,162,58,0.2), transparent 45%)' }} />
        <div className="relative flex items-center gap-2.5">
          <img src="/favicon.svg" className="h-10 w-10" alt="" />
          <span className="font-display text-2xl">Cafe Companion</span>
        </div>
        <div className="relative space-y-6">
          <h1 className="font-display text-5xl leading-tight">{staff ? 'Run a calmer counter.' : 'Your café, a little smarter.'}</h1>
          <ul className="space-y-3 text-cream-200">
            {(staff
              ? [[Coffee, 'Live order board with learned prep times'], [Timer, 'Guests see honest, updating wait times'], [BadgeCheck, 'Pre-orders released right on time']]
              : [[Coffee, 'Order by chatting, like talking to your barista'], [Timer, 'Live wait times and "ready when I arrive"'], [Sparkles, 'Picks for your taste, and people worth meeting']]
            ).map(([Icon, text], i) => {
              const I = Icon as typeof Coffee;
              return (
                <li key={i} className="flex items-center gap-3">
                  <I className="h-5 w-5 text-ember-500" /> {text as string}
                </li>
              );
            })}
          </ul>
        </div>
        <p className="relative text-xs text-bean-300">Demo app · payments are simulated</p>
      </div>

      <div className="flex items-center justify-center px-5 py-10">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <img src="/favicon.svg" className="h-9 w-9" alt="" />
            <span className="font-display text-xl">Cafe Companion</span>
          </div>
          {staff && <span className="mb-3 inline-block rounded-md bg-bean-900 px-2 py-1 text-[10px] font-bold tracking-wider text-cream-50 uppercase">Employee sign-in</span>}
          <h2 className="text-3xl">{staff ? 'Welcome back' : mode === 'signin' ? 'Welcome back' : 'Create your account'}</h2>
          <p className="mt-1 text-sm text-bean-500">
            {staff ? 'Sign in with the account your manager invited.' : 'Sign in to order, track and discover.'}
          </p>

          <button onClick={() => run('google', signInWithGoogle)} disabled={!!busy} className="btn-ghost mt-6 w-full">
            {busy === 'google' ? <Spinner className="h-4 w-4" /> : <GoogleMark />} Continue with Google
          </button>
          <div className="my-5 flex items-center gap-3 text-xs text-bean-300">
            <div className="h-px flex-1 bg-cream-300" /> or <div className="h-px flex-1 bg-cream-300" />
          </div>

          <form onSubmit={onSubmit} className="space-y-3">
            {!staff && mode === 'signup' && (
              <label className="relative block">
                <UserIcon className="absolute top-3 left-3 h-4 w-4 text-bean-300" />
                <input className="w-full pl-9" placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} required />
              </label>
            )}
            <label className="relative block">
              <Mail className="absolute top-3 left-3 h-4 w-4 text-bean-300" />
              <input className="w-full pl-9" type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
            </label>
            <label className="relative block">
              <Lock className="absolute top-3 left-3 h-4 w-4 text-bean-300" />
              <input className="w-full pl-9" type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} />
            </label>
            <ErrorNote>{error}</ErrorNote>
            <button type="submit" disabled={!!busy} className={`${staff ? 'btn-primary' : 'btn-accent'} w-full`}>
              {busy === 'email' && <Spinner className="h-4 w-4 text-white" />}
              {staff || mode === 'signin' ? 'Sign in' : 'Create account'}
            </button>
          </form>

          {!staff && (
            <p className="mt-4 text-center text-sm text-bean-500">
              {mode === 'signin' ? 'New here?' : 'Have an account?'}{' '}
              <button className="font-medium text-ember-600" onClick={() => setMode(mode === 'signin' ? 'signup' : 'signin')}>
                {mode === 'signin' ? 'Create an account' : 'Sign in'}
              </button>
            </p>
          )}
          {staff && (
            <p className="mt-4 text-center text-xs text-bean-500">
              First time? Accept your invite by signing in with the invited email (Google or a new password via the customer sign-up).
            </p>
          )}
          <p className="mt-8 text-center text-xs text-bean-500">
            {staff ? <Link to="/login" className="underline">Customer sign-in</Link> : <Link to="/staff/login" className="underline">Employee sign-in</Link>}
          </p>
        </div>
      </div>
    </div>
  );
}
