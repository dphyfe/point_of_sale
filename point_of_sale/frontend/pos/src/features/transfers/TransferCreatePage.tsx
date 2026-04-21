import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '../../lib/api';

interface Line {
    sku_id: string;
    qty: string;
    serial_ids: string;  // comma-separated
}

const blank: Line = { sku_id: '', qty: '1', serial_ids: '' };

export function TransferCreatePage() {
    const navigate = useNavigate();
    const [src, setSrc] = useState('');
    const [dst, setDst] = useState('');
    const [lines, setLines] = useState<Line[]>([{ ...blank }]);
    const create = useMutation({
        mutationFn: () =>
            api.post<{ id: string }>('/transfers', {
                source_location_id: src,
                destination_location_id: dst,
                lines: lines.map((l) => ({
                    sku_id: l.sku_id,
                    qty: l.qty,
                    serial_ids: l.serial_ids
                        ? l.serial_ids.split(',').map((s) => s.trim()).filter(Boolean)
                        : null,
                })),
            }),
        onSuccess: (r) => navigate(`/transfers/${r.id}`),
    });

    const setLine = (i: number, patch: Partial<Line>) =>
        setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));

    return (
        <section>
            <h2>New Transfer</h2>
            <label>
                Source location id <input value={src} onChange={(e) => setSrc(e.target.value)} />
            </label>
            <label>
                Destination location id <input value={dst} onChange={(e) => setDst(e.target.value)} />
            </label>
            <table>
                <thead>
                    <tr>
                        <th>SKU</th>
                        <th>Qty</th>
                        <th>Serial ids (comma-sep, must equal qty for serialized)</th>
                    </tr>
                </thead>
                <tbody>
                    {lines.map((l, i) => (
                        <tr key={i}>
                            <td>
                                <input value={l.sku_id} onChange={(e) => setLine(i, { sku_id: e.target.value })} />
                            </td>
                            <td>
                                <input
                                    type="number"
                                    value={l.qty}
                                    onChange={(e) => setLine(i, { qty: e.target.value })}
                                />
                            </td>
                            <td>
                                <input
                                    value={l.serial_ids}
                                    onChange={(e) => setLine(i, { serial_ids: e.target.value })}
                                />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
            <button onClick={() => setLines((ls) => [...ls, { ...blank }])}>+ Line</button>
            <button disabled={create.isPending} onClick={() => create.mutate()}>
                Create
            </button>
            {create.error && <p role="alert">{(create.error as Error).message}</p>}
        </section>
    );
}
