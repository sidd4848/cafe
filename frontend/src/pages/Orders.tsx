import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Receipt } from 'lucide-react';
import { api } from '@/lib/api';
import { dayClock, rupees } from '@/lib/format';
import type { Order } from '@/lib/types';
import { Empty, PageLoader, StatusPill } from '@/components/ui';

export default function Orders() {
  const [orders, setOrders] = useState<Order[] | null>(null);
  useEffect(() => {
    api.get<Order[]>('/orders').then(setOrders).catch(() => setOrders([]));
  }, []);
  if (!orders) return <PageLoader />;
  return (
    <div>
      <h1 className="mb-4 text-3xl">Your orders</h1>
      {orders.length === 0 ? (
        <Empty icon={<Receipt className="h-5 w-5" />} title="No orders yet">Your first cup is a chat away.</Empty>
      ) : (
        <div className="grid gap-2.5">
          {orders.map((o) => (
            <Link key={o.id} to={`/orders/${o.id}`} className="card flex items-center gap-3 p-3.5">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{o.items.map((l) => `${l.qty}× ${l.name}`).join(', ')}</p>
                <p className="text-xs text-bean-500">{dayClock(o.scheduledFor ?? o.createdAt)} · {rupees(o.total)}</p>
              </div>
              <StatusPill status={o.status} />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
