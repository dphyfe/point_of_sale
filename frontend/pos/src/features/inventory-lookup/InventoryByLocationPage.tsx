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
    const [locationId, setLocationId] = useState('');
    const q = useQuery({
        queryKey: ['inv-by-location', skuId.trim(), locationId.trim()],
        queryFn: () => {
            const params = new URLSearchParams();
            if (skuId.trim()) params.set('sku_id', skuId.trim());
            if (locationId.trim()) params.set('location_id', locationId.trim());
            const qs = params.toString();
            return api.get<BalanceRow[]>(`/inventory/balances${qs ? `?${qs}` : ''}`);
        },
    });
    const rows = q.data ?? [];
    return (
        <section>
            <h2>Inventory by Location</h2>
            <label>
                SKU id <input value={skuId} onChange={(e) => setSkuId(e.target.value)} />
            </label>
            <label>
                Location id{' '}
                <input value={locationId} onChange={(e) => setLocationId(e.target.value)} />
            </label>
            <button onClick={() => q.refetch()} disabled={q.isFetching}>
                {q.isFetching ? 'Loading…' : 'Refresh'}
            </button>
            {q.error && <p role="alert">{(q.error as Error).message}</p>}
            <p>
                {skuId.trim() || locationId.trim()
                    ? `Filtered balances (${rows.length})`
                    : `Recent balances (${rows.length})`}
            </p>
            {rows.length === 0 && !q.isFetching ? (
                <p>No balances found.</p>
            ) : (
                <table>
                    <thead>
                        <tr>
                            <th>SKU</th>
                            <th>Location</th>
                            <th>On hand</th>
                            <th>Reserved</th>
                            <th>Available</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((b, i) => (
                            <tr key={i}>
                                <td>{b.sku_id.slice(0, 8)}</td>
                                <td>{b.location_id.slice(0, 8)}</td>
                                <td>{b.on_hand}</td>
                                <td>{b.reserved}</td>
                                <td>{b.available}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </section>
    );
}
