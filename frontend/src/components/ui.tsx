import { useEffect, type ReactNode } from 'react';
import { Loader2, X } from 'lucide-react';

export function Spinner({ className = 'h-5 w-5' }: { className?: string }) {
  return <Loader2 className={`animate-spin text-bean-500 ${className}`} />;
}

export function PageLoader() {
  return (
    <div className="grid min-h-[50vh] place-items-center">
      <Spinner className="h-7 w-7" />
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  if (!children) return null;
  return <div className="rounded-xl bg-berry-100 px-3 py-2 text-sm text-berry-600">{children}</div>;
}

export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal>
      <div className="absolute inset-0 bg-bean-950/40 backdrop-blur-[2px]" onClick={onClose} />
      <div className="rise relative max-h-[90vh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-cream-50 p-5 pb-8 shadow-xl sm:rounded-3xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-xl">{title}</h3>
          <button onClick={onClose} className="rounded-full p-1.5 text-bean-500 hover:bg-cream-200" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center gap-2 px-6 py-10 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-full bg-cream-200 text-bean-700">{icon}</div>
      <p className="font-display text-lg">{title}</p>
      {children && <div className="text-sm text-bean-500">{children}</div>}
    </div>
  );
}

export function StatusPill({ status }: { status: string }) {
  const styles: Record<string, string> = {
    scheduled: 'bg-honey-100 text-bean-800',
    placed: 'bg-cream-200 text-bean-800',
    in_progress: 'bg-ember-100 text-ember-600',
    ready: 'bg-leaf-100 text-leaf-600',
    collected: 'bg-cream-200 text-bean-500',
    cancelled: 'bg-berry-100 text-berry-600',
  };
  const label: Record<string, string> = {
    scheduled: 'Pre-ordered', placed: 'Queued', in_progress: 'Making', ready: 'Ready',
    collected: 'Collected', cancelled: 'Cancelled',
  };
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${styles[status] ?? ''}`}>{label[status] ?? status}</span>;
}
