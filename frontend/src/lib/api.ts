import { auth } from './firebase';
import { config } from './config';

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// In-flight request count, so a global progress bar can show that the app is working.
let inflight = 0;
const listeners = new Set<(n: number) => void>();
export function onInflight(fn: (n: number) => void): () => void {
  listeners.add(fn);
  fn(inflight);
  return () => {
    listeners.delete(fn);
  };
}
function bump(d: number) {
  inflight += d;
  listeners.forEach((fn) => fn(inflight));
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  bump(1);
  try {
    return await send<T>(method, path, body);
  } finally {
    bump(-1);
  }
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const user = auth.currentUser;
  if (!user) throw new ApiError(401, 'Not signed in');
  const token = await user.getIdToken();
  const res = await fetch(`${config.apiUrl}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data.detail === 'string') msg = data.detail;
      else if (Array.isArray(data.detail)) msg = data.detail.map((d: { msg: string }) => d.msg).join(', ');
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(p: string) => request<T>('GET', p),
  post: <T>(p: string, b?: unknown) => request<T>('POST', p, b ?? {}),
  put: <T>(p: string, b: unknown) => request<T>('PUT', p, b),
  patch: <T>(p: string, b: unknown) => request<T>('PATCH', p, b),
  del: <T>(p: string) => request<T>('DELETE', p),
};
