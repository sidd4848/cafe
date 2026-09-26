import { NavLink, Navigate, Outlet, useLocation } from 'react-router-dom';
import { Armchair, Coffee, Compass, Home, LayoutGrid, LogOut, QrCode, Sparkles, Timer, User, Users, UtensilsCrossed } from 'lucide-react';
import { isStaffRole, useAuth } from '@/context/AuthContext';
import { WaitBadge } from './WaitBadge';
import { PageLoader } from './ui';
import { SessionProvider } from '@/context/SessionContext';
import { CartBar, CheckoutSheet } from './Checkout';

function Brand({ to = '/' }: { to?: string }) {
  return (
    <NavLink to={to} className="flex items-center gap-2">
      <img src="/favicon.svg" alt="" className="h-8 w-8" />
      <span className="font-display text-lg leading-none">Cafe Companion</span>
    </NavLink>
  );
}

export function RequireCustomer() {
  const { user, me, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <PageLoader />;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  if (!me) return <PageLoader />;
  if (!me.onboarded && loc.pathname !== '/onboarding') return <Navigate to={`/onboarding?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  return <Outlet />;
}

export function RequireStaff() {
  const { user, me, loading } = useAuth();
  if (loading) return <PageLoader />;
  if (!user) return <Navigate to="/staff/login" replace />;
  if (!me) return <PageLoader />;
  if (!isStaffRole(me.role)) return <Navigate to="/staff/login?denied=1" replace />;
  return <Outlet />;
}

const tabs = [
  { to: '/', label: 'Home', icon: Home, end: true },
  { to: '/order', label: 'Order', icon: Coffee },
  { to: '/discover', label: 'Discover', icon: Compass },
  { to: '/wait', label: 'Wait', icon: Timer },
  { to: '/connect', label: 'Connect', icon: Sparkles },
];

export function CustomerLayout() {
  return (
    <SessionProvider>
      <CustomerShell />
    </SessionProvider>
  );
}

function CustomerShell() {
  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col">
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-cream-200 bg-cream-100/90 px-4 py-3 backdrop-blur">
        <Brand />
        <div className="flex items-center gap-2">
          <WaitBadge compact />
          <NavLink to="/profile" className="rounded-full p-1.5 text-bean-700 hover:bg-cream-200" aria-label="Profile">
            <User className="h-5 w-5" />
          </NavLink>
        </div>
      </header>
      <main className="flex-1 px-4 pt-4 pb-40">
        <Outlet />
      </main>
      <CartBar />
      <CheckoutSheet />
      <nav className="fixed inset-x-0 bottom-0 z-30 mx-auto max-w-md border-t border-cream-200 bg-cream-50/95 pb-[env(safe-area-inset-bottom)] backdrop-blur">
        <div className="grid grid-cols-5">
          {tabs.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex flex-col items-center gap-0.5 py-2.5 text-[11px] font-medium ${isActive ? 'text-ember-600' : 'text-bean-500'}`
              }
            >
              <Icon className="h-5 w-5" />
              {label}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}

export function StaffLayout() {
  const { me, signOut } = useAuth();
  const links = [
    { to: '/staff', label: 'Orders', icon: LayoutGrid, end: true },
    { to: '/staff/floor', label: 'Floor', icon: Armchair },
    { to: '/staff/menu', label: 'Menu', icon: UtensilsCrossed },
    { to: '/staff/qr', label: 'Table QR', icon: QrCode },
    ...(me?.role === 'manager' ? [{ to: '/staff/team', label: 'Team', icon: Users }] : []),
  ];
  return (
    <div className="min-h-screen bg-cream-100">
      <header className="sticky top-0 z-30 border-b border-bean-800 bg-bean-900 text-cream-50">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <div className="flex items-center gap-2">
            <img src="/favicon.svg" alt="" className="h-7 w-7" />
            <span className="font-display text-lg">Cafe Companion</span>
            <span className="rounded-md bg-ember-600 px-1.5 py-0.5 text-[10px] font-bold tracking-wider uppercase">Staff</span>
          </div>
          <nav className="flex flex-1 gap-1 overflow-x-auto scroll-thin">
            {links.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm ${isActive ? 'bg-bean-700 text-white' : 'text-bean-300 hover:text-white'}`
                }
              >
                <Icon className="h-4 w-4" /> {label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-3 text-sm text-bean-300">
            <span className="hidden sm:inline">{me?.displayName} · {me?.role}</span>
            <button onClick={signOut} className="flex items-center gap-1 rounded-lg px-2 py-1.5 hover:text-white">
              <LogOut className="h-4 w-4" /> Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-5">
        <Outlet />
      </main>
    </div>
  );
}

export { Brand };
