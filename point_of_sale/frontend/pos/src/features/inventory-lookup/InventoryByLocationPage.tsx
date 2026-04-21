import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../lib/api';

interface BalanceRow {
    sku_id: string;
    location_id: string;
    on_hand: string;
    reserved: string;
    available: string;
}

export function InventoryByLocationPage() {
    const [skuId, setSkuId] = useState('');
    const q = useQuery({
        queryKey: ['inv-by-location', skuId],
        queryFn: () =>
            api.get<BalanceRow[]>(`/inventory/balances?sku_id=${encodeURIComponent(skuId)}`),
        enabled: !!skuId,
    });
    return (
        <section>
            <h2>Inventory by Location</h2>
            <label>
                SKU id <input value={skuId} onChange={(e) => setSkuId(e.target.value)} />
            </label>
            <table>
                <thead>
                    <tr>
                        <th>Location</th>
                        <th>On hand</th>
                        <th>Reserved</th>
                        <th>Available</th>
                    </tr>
                </thead>
                <tbody>
                    {q.data?.map((b, i) => (
                        <tr key={i}>
                            <td>{b.location_id.slice(0, 8)}</td>
                            <td>{b.on_hand}</td>
                            <td>{b.reserved}</td>
                            <td>{b.available}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </section>
    );
}
