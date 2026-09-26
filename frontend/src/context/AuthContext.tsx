import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import {
  createUserWithEmailAndPassword,
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut as fbSignOut,
  updateProfile,
  type User,
} from 'firebase/auth';
import { auth } from '@/lib/firebase';
import { api } from '@/lib/api';
import type { Me } from '@/lib/types';

interface AuthState {
  user: User | null;
  me: Me | null;
  loading: boolean;
  error: string | null;
  signInWithGoogle: () => Promise<void>;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  registerWithEmail: (name: string, email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshMe: () => Promise<Me | null>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshMe = useCallback(async () => {
    try {
      const m = await api.get<Me>('/me');
      // The API may have just granted a staff role (invite accepted). Refresh the ID token
      // so the new `role` claim reaches Firestore rules for the barista board listener.
      if (m.roleChanged) await auth.currentUser?.getIdToken(true);
      setMe(m);
      setError(null);
      return m;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  }, []);

  useEffect(
    () =>
      onAuthStateChanged(auth, async (u) => {
        setUser(u);
        if (u) await refreshMe();
        else setMe(null);
        setLoading(false);
      }),
    [refreshMe],
  );

  const value: AuthState = {
    user,
    me,
    loading,
    error,
    refreshMe,
    signInWithGoogle: async () => {
      await signInWithPopup(auth, new GoogleAuthProvider());
    },
    signInWithEmail: async (email, password) => {
      await signInWithEmailAndPassword(auth, email, password);
    },
    registerWithEmail: async (name, email, password) => {
      const cred = await createUserWithEmailAndPassword(auth, email, password);
      if (name) await updateProfile(cred.user, { displayName: name });
    },
    signOut: async () => {
      await fbSignOut(auth);
    },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAuth outside AuthProvider');
  return v;
}

export const isStaffRole = (role?: string) => role === 'staff' || role === 'manager';

export function friendlyAuthError(e: unknown): string {
  const code = (e as { code?: string }).code ?? '';
  const map: Record<string, string> = {
    'auth/invalid-credential': 'Email or password is incorrect.',
    'auth/email-already-in-use': 'That email already has an account. Sign in instead.',
    'auth/weak-password': 'Use at least 6 characters.',
    'auth/popup-closed-by-user': 'Sign-in was cancelled.',
    'auth/unauthorized-domain': 'This site is not authorised for sign-in yet.',
  };
  return map[code] ?? (e as Error).message;
}
