import { useEffect, useState } from 'react';
import QRCode from 'qrcode';
import { Printer } from 'lucide-react';
import { api } from '@/lib/api';
import { config } from '@/lib/config';
import { PageLoader } from '@/components/ui';

interface Code { id: string; label: string; seats: number; zone: string; token: string }

/** Today's table QR codes. They rotate daily, so print (or show on a table tablet) each morning. */
export default function TableQR() {
  const cafeId = config.cafeId;
  const [codes, setCodes] = useState<(Code & { url: string; img: string })[] | null>(null);

  useEffect(() => {
    api.get<Code[]>(`/staff/cafes/${cafeId}/table-codes`).then(async (list) => {
      const withImg = await Promise.all(list.sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true })).map(async (c) => {
        const url = `${window.location.origin}/checkin?cafe=${cafeId}&table=${c.id}&t=${c.token}`;
        return { ...c, url, img: await QRCode.toDataURL(url, { margin: 1, width: 360, color: { dark: '#2b1d14', light: '#ffffff' } }) };
      }));
      setCodes(withImg);
    });
  }, [cafeId]);

  if (!codes) return <PageLoader />;
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3 print:hidden">
        <div className="mr-auto">
          <h1 className="text-3xl">Table QR codes</h1>
          <p className="text-sm text-bean-500">Scan to order to the table, pay the bill, or check in to Connect. Codes change every day.</p>
        </div>
        <button className="btn-primary" onClick={() => window.print()}><Printer className="h-4 w-4" /> Print</button>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {codes.map((c) => (
          <a key={c.id} href={c.url} target="_blank" rel="noreferrer" className="card flex flex-col items-center p-4 text-center break-inside-avoid">
            <img src={c.img} alt={`QR for ${c.label}`} className="w-full max-w-[180px]" />
            <p className="mt-2 font-display text-lg">{c.label}</p>
            <p className="text-xs text-bean-500">Scan to order · pay · connect</p>
          </a>
        ))}
      </div>
    </div>
  );
}
