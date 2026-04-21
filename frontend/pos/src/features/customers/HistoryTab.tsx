import { useEffect, useState } from 'react';
import { api } from '../../lib/api';

interface HistoryItem {
    id: string;
    kind: 'sale' | 'return' | 'exchange' | 'service_order';
    occurred_at: string;
    store_name: string | null;
    register_name: string | null;
    cashier_user_id: string | null;
    total: string | null;
    refund_total: string | null;
    summary: string | null;
}

interface HistoryResponse {
    items: HistoryItem[];
    next_cursor: string | null;
}

interface HistoryDetailLine {
    sku_id: string;
    sku_code: string | null;
    description: string | null;
    qty: string;
    unit_price: string | null;
    line_total: string | null;
    serial_numbers: string[];
}

interface HistoryDetail extends HistoryItem {
    lines: HistoryDetailLine[];
}

export function HistoryTab({ customerId }: { customerId: string }) {
    const [data, setData] = useState<HistoryResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [kindFilter, setKindFilter] = useState<string>('');
    const [selected, setSelected] = useState<HistoryDetail | null>(null);

    const load = async () => {
        try {
            const params = new URLSearchParams();
            if (kindFilter) params.set('kinds', kindFilter);
            const r = await api.get<HistoryResponse>(
                `/customers/${customerId}/history?${params.toString()}`,
            );
            setData(r);
        } catch (e) {
            setError((e as Error).message);
        }
    };

    useEffect(() => {
        void load();
    }, [customerId, kindFilter]);

    const openDetail = async (kind: string, txnId: string) => {
        try {
            const r = await api.get<HistoryDetail>(
                `/customers/${customerId}/history/${kind}/${txnId}`,
            );
            setSelected(r);
        } catch (e) {
            setError((e as Error).message);
        }
    };

    const reprintReceipt = async (txnId: string) => {
        try {
            await api.post(`/receipts/${txnId}/reprint`, {});
            alert('Reprint requested.');
        } catch (e) {
            alert(`Reprint failed: ${(e as Error).message}`);
        }
    };

    const emailReceipt = async (txnId: string, kind: string) => {
        try {
            await api.post(`/customers/${customerId}/messages`, {
                template_code: 'receipt_copy',
                channel: 'email',
                purpose: 'transactional',
                to_address: '',
                related_transaction_id: txnId,
                related_transaction_kind: kind,
                client_request_id: crypto.randomUUID(),
            });
            alert('Receipt emailed.');
        } catch (e) {
            alert(`Email failed: ${(e as Error).message}`);
        }
    };

    return (
        <section>
            <h3>Transaction History</h3>
            <label>
                Kind:&nbsp;
                <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)}>
                    <option value="">All</option>
                    <option value="sale">Sales</option>
                    <option value="return">Returns</option>
                    <option value="exchange">Exchanges</option>
                    <option value="service_order">Service orders</option>
                </select>
            </label>
            {error && <p role="alert">{error}</p>}
            {data && (
                <table>
                    <thead>
                        <tr>
                            <th>When</th>
                            <th>Kind</th>
                            <th>Store</th>
                            <th>Total</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {data.items.map((it) => (
                            <tr key={`${it.kind}:${it.id}`}>
                                <td>{new Date(it.occurred_at).toLocaleString()}</td>
                                <td>{it.kind}</td>
                                <td>{it.store_name ?? ''}</td>
                                <td>{it.total ?? it.refund_total ?? ''}</td>
                                <td>
                                    <button onClick={() => openDetail(it.kind, it.id)}>View</button>
                                    <button onClick={() => reprintReceipt(it.id)}>Reprint</button>
                                    <button onClick={() => emailReceipt(it.id, it.kind)}>
                                        Email receipt
                                    </button>
                                    {it.kind === 'sale' && (
                                        <a href={`#/returns/new?from=${it.id}`}>Start return</a>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
            {selected && (
                <aside>
                    <h4>{selected.kind} {selected.id}</h4>
                    <button onClick={() => setSelected(null)}>Close</button>
                    <table>
                        <thead>
                            <tr>
                                <th>SKU</th>
                                <th>Description</th>
                                <th>Qty</th>
                                <th>Total</th>
                                <th>Serials</th>
                            </tr>
                        </thead>
                        <tbody>
                            {selected.lines.map((l, idx) => (
                                <tr key={idx}>
                                    <td>{l.sku_code}</td>
                                    <td>{l.description}</td>
                                    <td>{l.qty}</td>
                                    <td>{l.line_total ?? ''}</td>
                                    <td>{l.serial_numbers.join(', ')}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </aside>
            )}
        </section>
    );
}
