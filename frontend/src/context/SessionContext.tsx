import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { api } from '@/lib/api';
import { config } from '@/lib/config';
import type { Menu, Session } from '@/lib/types';

interface SessionState {
  cafeId: string;
  session: Session | null;
  menu: Menu | null;
  busy: boolean;
  addItem: (itemId: string, modifiers?: Record<string, string>, qty?: number) => Promise<void>;
  cartOp: (op: Record<string, unknown>) => Promise<void>;
  chat: (text: string) => Promise<void>;
  setPickup: (iso: string | null) => Promise<void>;
  reload: () => Promise<void>;
  replace: (s: Session) => void;
  checkoutOpen: boolean;
  setCheckoutOpen: (v: boolean) => void;
}

const Ctx = createContext<SessionState | null>(null);

/** The guest's draft order (chat + cart + pickup time), shared by every customer page. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const cafeId = config.cafeId;
  const [session, setSession] = useState<Session | null>(null);
  const [menu, setMenu] = useState<Menu | null>(null);
  const [busy, setBusy] = useState(false);
  const [checkoutOpen, setCheckoutOpen] = useState(false);

  const reload = useCallback(async () => {
    const [s, m] = await Promise.all([api.get<Session>(`/cafes/${cafeId}/session`), api.get<Menu>(`/cafes/${cafeId}/menu`)]);
    setSession(s);
    setMenu(m);
  }, [cafeId]);

  useEffect(() => {
    reload().catch(() => undefined);
  }, [reload]);

  const wrap = async (fn: () => Promise<Session>) => {
    setBusy(true);
    try {
      setSession(await fn());
    } finally {
      setBusy(false);
    }
  };

  const value: SessionState = {
    cafeId,
    session,
    menu,
    busy,
    reload,
    replace: setSession,
    checkoutOpen,
    setCheckoutOpen,
    cartOp: (op) => wrap(() => api.post(`/cafes/${cafeId}/session/cart`, op)),
    addItem: (itemId, modifiers = {}, qty = 1) => wrap(() => api.post(`/cafes/${cafeId}/session/cart`, { op: 'add', itemId, modifiers, qty })),
    chat: async (text) => {
      // Show the guest's message immediately; the server returns the full thread.
      setSession((s) => (s ? { ...s, messages: [...s.messages, { role: 'user', text, at: new Date().toISOString() }] } : s));
      try {
        await wrap(() => api.post(`/cafes/${cafeId}/session/chat`, { text }));
      } catch (e) {
        setSession((s) => (s ? { ...s, messages: [...s.messages, { role: 'assistant', text: `⚠️ ${(e as Error).message}`, at: new Date().toISOString() }] } : s));
      }
    },
    setPickup: (iso) => wrap(() => api.put(`/cafes/${cafeId}/session/pickup`, { pickupAt: iso })),
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useSession outside SessionProvider');
  return v;
}
