import { useEffect, useState } from 'react';
import { doc, onSnapshot, Timestamp, type DocumentData, type Query } from 'firebase/firestore';
import { onSnapshot as onQuerySnapshot } from 'firebase/firestore';
import { firestore } from './firebase';
import { config } from './config';
import type { LiveStats } from './types';

/** Re-render every `ms` so countdowns and "x min" labels stay current. */
export function useNow(ms = 1000): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}

/** Firestore Timestamps -> ISO strings (one level of nesting), matching the API's shape. */
export function isoify(data: DocumentData): DocumentData {
  const out: DocumentData = {};
  for (const [k, v] of Object.entries(data)) {
    if (v instanceof Timestamp) out[k] = v.toDate().toISOString();
    else if (v && typeof v === 'object' && !Array.isArray(v)) out[k] = isoify(v);
    else out[k] = v;
  }
  return out;
}

/** Firestore Timestamps -> Date (deep), for Connect docs the UI does date maths on. */
export function dateify(data: DocumentData): DocumentData {
  const out: DocumentData = {};
  for (const [k, v] of Object.entries(data)) {
    if (v instanceof Timestamp) out[k] = v.toDate();
    else if (v && typeof v === 'object' && !Array.isArray(v)) out[k] = dateify(v);
    else out[k] = v;
  }
  return out;
}

/**
 * Unsubscribe without letting a Firestore SDK failure escape into React's cleanup phase:
 * an exception there unmounts the whole app, which is far worse than a stale listener.
 */
function safeUnsub(unsub: () => void) {
  return () => {
    try {
      unsub();
    } catch (e) {
      console.warn('Listener cleanup failed', e);
    }
  };
}

function safeListen(start: () => () => void, onError: (msg: string) => void): () => void {
  try {
    return safeUnsub(start());
  } catch (e) {
    onError((e as Error).message);
    return () => undefined;
  }
}

export function useDoc<T>(path: string | null, map: (d: DocumentData) => DocumentData = isoify) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!path) return;
    return safeListen(() => onSnapshot(
      doc(firestore, path),
      (snap) => setData(snap.exists() ? ({ id: snap.id, ...map(snap.data()) } as T) : null),
      (e) => setError(e.message),
    ), setError);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);
  return { data, error };
}

export function useQuery<T>(q: Query | null, key: string, map: (d: DocumentData) => DocumentData = isoify) {
  const [data, setData] = useState<T[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!q) return;
    return safeListen(() => onQuerySnapshot(
      q,
      (snap) => setData(snap.docs.map((d) => ({ id: d.id, ...map(d.data()) }) as T)),
      (e) => setError(e.message),
    ), setError);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return { data, error };
}

export function useLiveStats(cafeId = config.cafeId) {
  return useDoc<LiveStats>(`cafes/${cafeId}/stats/live`).data;
}
