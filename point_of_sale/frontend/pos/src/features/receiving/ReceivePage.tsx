import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { usePurchaseOrder } from '../purchase-orders/usePurchaseOrders';
import { useReceipt, type ReceiptLineInput } from './useReceipt';

interface DraftLine {
    po_line_id: string;
    ordered_qty: string;
    received_qty: string;
    serial_values: string[]; // empty for non-serial
    lot_code: string;
    is_serialized: boolean; // user toggle (PO line metadata not surfaced in MVP)
    is_lot: boolean;
}

export function ReceivePage() {
    const { poId = '' } = useParams();
    const { data: po, isLoading } = usePurchaseOrder(poId);
    const receive = useReceipt();
    const [locationId, setLocationId] = useState('');
    const [draft, setDraft] = useState<Record<string, DraftLine>>({});
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    const ensureDraft = (id: string, ordered: string): DraftLine =>
        draft[id] ?? {
            po_line_id: id,
            ordered_qty: ordered,
            received_qty: '0',
            serial_values: [],
            lot_code: '',
            is_serialized: false,
            is_lot: false,
        };

    const setLine = (id: string, patch: Partial<DraftLine>) => {
        setDraft((d) => ({ ...d, [id]: { ...ensureDraft(id, '0'), ...patch } }));
    };

    const addSerial = (id: string, value: string) => {
        if (!value) return;
        setDraft((d) => {
            const cur = d[id];
            if (!cur) return d;
            if (cur.serial_values.includes(value)) return d;
            return { ...d, [id]: { ...cur, serial_values: [...cur.serial_values, value] } };
        });
    };

    const submit = async () => {
        setError(null);
        setSuccess(null);
        if (!locationId) {
            setError('Pick a destination location first.');
            return;
        }
        const lines: ReceiptLineInput[] = Object.values(draft)
            .filter((d) => Number(d.received_qty) > 0)
            .map((d) => {
                // Serial-tracked SKUs: scanned serial count must equal received qty.
                if (d.is_serialized && d.serial_values.length !== Number(d.received_qty)) {
                    throw new Error(`Line ${d.po_line_id}: serial count must equal received qty`);
                }
                if (d.is_lot && !d.lot_code) {
                    throw new Error(`Line ${d.po_line_id}: lot code required`);
                }
                return {
                    po_line_id: d.po_line_id,
                    received_qty: d.received_qty,
                    serial_values: d.is_serialized ? d.serial_values : [],
                    lot_code: d.is_lot ? d.lot_code : null,
                };
            });
        if (!lines.length) {
            setError('Nothing to receive.');
            return;
        }
        try {
            const res = await receive.mutateAsync({
                purchase_order_id: poId,
                location_id: locationId,
                lines,
            });
            setSuccess(`Receipt ${res.id} posted.`);
            setDraft({});
        } catch (e) {
            setError((e as Error).message);
        }
    };

    if (!poId) return <p>Missing PO id in URL.</p>;
    if (isLoading || !po) return <p>Loading…</p>;

    return (
        <section>
            <h2>Receive against PO {po.po_number}</h2>
            <label>
                Destination location
                <input value={locationId} onChange={(e) => setLocationId(e.target.value)} />
            </label>
            <table>
                <thead>
                    <tr>
                        <th>SKU</th>
                        <th>Ordered</th>
                        <th>Already Received</th>
                        <th>Receive Now</th>
                        <th>Tracking</th>
                        <th>Serials / Lot</th>
                    </tr>
                </thead>
                <tbody>
                    {po.lines.map((l) => {
                        const d = ensureDraft(l.id, l.ordered_qty);
                        return (
                            <tr key={l.id}>
                                <td>{l.sku_id}</td>
                                <td>{l.ordered_qty}</td>
                                <td>{l.received_qty}</td>
                                <td>
                                    <input
                                        type="number"
                                        value={d.received_qty}
                                        onChange={(e) => setLine(l.id, { received_qty: e.target.value })}
                                    />
                                </td>
                                <td>
                                    <label>
                                        <input
                                            type="checkbox"
                                            checked={d.is_serialized}
                                            onChange={(e) => setLine(l.id, { is_serialized: e.target.checked, is_lot: false })}
                                        />
                                        serial
                                    </label>
                                    <label>
                                        <input
                                            type="checkbox"
                                            checked={d.is_lot}
                                            onChange={(e) => setLine(l.id, { is_lot: e.target.checked, is_serialized: false })}
                                        />
                                        lot
                                    </label>
                                </td>
                                <td>
                                    {d.is_serialized && (
                                        <SerialList
                                            serials={d.serial_values}
                                            onAdd={(v) => addSerial(l.id, v)}
                                            onRemove={(v) =>
                                                setLine(l.id, { serial_values: d.serial_values.filter((s) => s !== v) })
                                            }
                                        />
                                    )}
                                    {d.is_lot && (
                                        <input
                                            placeholder="lot code"
                                            value={d.lot_code}
                                            onChange={(e) => setLine(l.id, { lot_code: e.target.value })}
                                        />
                                    )}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
            <button disabled={receive.isPending} onClick={submit}>
                Post Receipt
            </button>
            {error && <p role="alert">{error}</p>}
            {success && <p role="status">{success}</p>}
        </section>
    );
}

function SerialList({
    serials,
    onAdd,
    onRemove,
}: {
    serials: string[];
    onAdd: (v: string) => void;
    onRemove: (v: string) => void;
}) {
    const [val, setVal] = useState('');
    return (
        <div>
            <input
                placeholder="scan serial"
                aria-label="scan serial"
                value={val}
                onChange={(e) => setVal(e.target.value)}
                onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                        onAdd(val.trim());
                        setVal('');
                    }
                }}
            />
            <ul>
                {serials.map((s) => (
                    <li key={s}>
                        {s} <button onClick={() => onRemove(s)}>×</button>
                    </li>
                ))}
            </ul>
        </div>
    );
}
