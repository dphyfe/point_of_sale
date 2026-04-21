import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCreatePurchaseOrder, type PoLineInput } from './usePurchaseOrders';

const emptyLine: PoLineInput = { sku_id: '', ordered_qty: '1', unit_cost: '0' };

export function PoCreatePage() {
    const nav = useNavigate();
    const create = useCreatePurchaseOrder();
    const [vendorId, setVendorId] = useState('');
    const [poNumber, setPoNumber] = useState('');
    const [lines, setLines] = useState<PoLineInput[]>([{ ...emptyLine }]);

    const setLine = (i: number, patch: Partial<PoLineInput>) => {
        setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));
    };

    const submit = async () => {
        const res = await create.mutateAsync({ vendor_id: vendorId, po_number: poNumber, lines });
        nav(`/pos/${res.id}`);
    };

    return (
        <section>
            <h2>New Purchase Order</h2>
            <label>
                Vendor ID
                <input value={vendorId} onChange={(e) => setVendorId(e.target.value)} />
            </label>
            <label>
                PO Number
                <input value={poNumber} onChange={(e) => setPoNumber(e.target.value)} />
            </label>
            <h3>Lines</h3>
            {lines.map((l, i) => (
                <div key={i} style={{ display: 'flex', gap: 8 }}>
                    <input
                        placeholder="SKU ID"
                        value={l.sku_id}
                        onChange={(e) => setLine(i, { sku_id: e.target.value })}
                    />
                    <input
                        type="number"
                        placeholder="Qty"
                        value={l.ordered_qty}
                        onChange={(e) => setLine(i, { ordered_qty: e.target.value })}
                    />
                    <input
                        type="number"
                        placeholder="Unit Cost"
                        value={l.unit_cost}
                        onChange={(e) => setLine(i, { unit_cost: e.target.value })}
                    />
                </div>
            ))}
            <button onClick={() => setLines((ls) => [...ls, { ...emptyLine }])}>+ Line</button>
            <button disabled={create.isPending} onClick={submit}>
                Create PO
            </button>
        </section>
    );
}
