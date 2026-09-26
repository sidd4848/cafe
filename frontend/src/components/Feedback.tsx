import { Component, useEffect, useState, type ReactNode } from 'react';
import { RotateCw } from 'lucide-react';
import { onInflight } from '@/lib/api';

/** Thin animated bar at the top of the screen while any API request is in flight. */
export function TopLoader() {
  const [n, setN] = useState(0);
  const [show, setShow] = useState(false);
  useEffect(() => onInflight(setN), []);
  useEffect(() => {
    // Short delay so instant requests don't flash the bar.
    if (!n) {
      setShow(false);
      return;
    }
    const id = setTimeout(() => setShow(true), 150);
    return () => clearTimeout(id);
  }, [n]);
  return (
    <div className={`pointer-events-none fixed inset-x-0 top-0 z-[60] h-[3px] overflow-hidden transition-opacity ${show ? 'opacity-100' : 'opacity-0'}`} role="progressbar" aria-hidden={!show} aria-label="Loading">
      <div className="loader-bar h-full w-1/3 rounded-full bg-ember-500" />
    </div>
  );
}

/** Replaces a crashed screen with a way back, instead of an empty page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error) {
    console.error('UI crashed:', error);
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
        <img src="/favicon.svg" alt="" className="h-12 w-12" />
        <h1 className="text-2xl">Something went wrong</h1>
        <p className="text-sm text-bean-500">Your cart and orders are saved. Reload to pick up where you left off.</p>
        <button className="btn-primary mt-2" onClick={() => window.location.reload()}><RotateCw className="h-4 w-4" /> Reload</button>
        <p className="mt-4 text-[11px] text-bean-300">{this.state.error.message}</p>
      </div>
    );
  }
}
