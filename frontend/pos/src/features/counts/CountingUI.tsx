import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { api } from '../../lib/api';

interface SessionInfo {
    id: string;
    state: string;
    hide_system_qty: boolean;
}
interface Snapshot {
    sku_id: string;
    location_id: string;
    on_hand_at_open: string;
}

export function CountingUI() {
    const { id } = useParams();
    const [skuId, setSkuId] = useState('');
    const [locationId, setLocationId] = useState('');
    const [qty, setQty] = useState('1');
    const [counterUserId, setCounterUserId] = useState('');
    const [serial, setSerial] = useState('');

    const session = useQuery({
        queryKey: ['count-session', id],
        queryFn: () => api.get<SessionInfo>(`/count-sessions/${id}`),
        enabled: !!id,
    });
    const snapshots = useQuery({
        queryKey: ['count-session-snapshots', id],
        queryFn: () => api.get<Snapshot[]>(`/count-sessions/${id}/snapshots`),
        enabled: !!id && session.data?.hide_system_qty === false,
    });

    const submit = useMutation({
        mutationFn: () =>
            api.post(`/count-sessions/${id}/entries`, {
                entries: [
                    {
                        sku_id: skuId,
                        location_id: locationId,
                        counted_qty: qty,
                        counter_user_id: counterUserId,
                        serial_value: serial || null,
                    },
                ],
            }),
        onSuccess: () => {
            setSkuId('');
            setQty('1');
            setSerial('');
        },
    });

    const hideSystem = session.data?.hide_system_qty ?? true;

    return (
        <section>
            <h2>Counting — Session {id?.slice(0, 8)}</h2>
            <p data-testid="hide-system-mode">
                {hideSystem ? 'Blind count: system qty hidden' : 'Open count'}
            </p>
            <label>
                Counter user id{' '}
                <input value={counterUserId} onChange={(e) => setCounterUserId(e.target.value)} />
            </label>
            <label>
                Location id{' '}
                <input value={locationId} onChange={(e) => setLocationId(e.target.value)} />
            </label>
            <label>
                Scan/enter SKU{' '}
                <input
                    aria-label="scan sku"
                    value={skuId}
                    onChange={(e) => setSkuId(e.target.value)}
                />
            </label>
            <label>
                Qty <input type="number" value={qty} onChange={(e) => setQty(e.target.value)} />
            </label>
            <label>
                Serial (if serialized){' '}
                <input value={serial} onChange={(e) => setSerial(e.target.value)} />
            </label>
            <button disabled={submit.isPending} onClick={() => submit.mutate()}>
                Add Count
            </button>
            {submit.isSuccess && <p role="status">Saved.</p>}

            {!hideSystem && snapshots.data && (
                <details>
                    <summary>System on-hand at open</summary>
                    <ul data-testid="system-qty-list">
                        {snapshots.data.map((s, i) => (
                            <li key={i}>
                                {s.sku_id.slice(0, 8)} @ {s.location_id.slice(0, 8)}: {s.on_hand_at_open}
                            </li>
                        ))}
                    </ul>
                </details>
            )}
        </section>
    );
}
