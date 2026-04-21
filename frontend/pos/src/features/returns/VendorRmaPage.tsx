import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api } from '../../lib/api';

export function VendorRmaPage() {
    const [vendorId, setVendorId] = useState('');
    const [holdingLocId, setHoldingLocId] = useState('');
    const [originatingPoId, setOriginatingPoId] = useState('');
    const [skuId, setSkuId] = useState('');
    const [qty, setQty] = useState('1');
    const [serialId, setSerialId] = useState('');
    const [rmaId, setRmaId] = useState('');

    const create = useMutation({
        mutationFn: () =>
            api.post<{ id: string }>('/vendor-rmas', {
                vendor_id: vendorId,
                holding_location_id: holdingLocId,
                originating_po_id: originatingPoId || null,
                lines: [
                    {
                        sku_id: skuId,
                        qty,
                        serial_id: serialId || null,
                        unit_cost: '0',
                    },
                ],
            }),
        onSuccess: (r) => setRmaId(r.id),
    });
    const ship = useMutation({ mutationFn: () => api.post(`/vendor-rmas/${rmaId}/ship`, {}) });
    const closeR = useMutation({ mutationFn: () => api.post(`/vendor-rmas/${rmaId}/close`, {}) });

    return (
        <section>
            <h2>Vendor RMA</h2>
            <fieldset>
                <legend>Create</legend>
                <label>
                    Vendor id <input value={vendorId} onChange={(e) => setVendorId(e.target.value)} />
                </label>
                <label>
                    Holding location id{' '}
                    <input value={holdingLocId} onChange={(e) => setHoldingLocId(e.target.value)} />
                </label>
                <label>
                    Originating PO id{' '}
                    <input value={originatingPoId} onChange={(e) => setOriginatingPoId(e.target.value)} />
                </label>
                <label>
                    SKU id <input value={skuId} onChange={(e) => setSkuId(e.target.value)} />
                </label>
                <label>
                    Qty{' '}
                    <input type="number" value={qty} onChange={(e) => setQty(e.target.value)} />
                </label>
                <label>
                    Serial id (optional){' '}
                    <input value={serialId} onChange={(e) => setSerialId(e.target.value)} />
                </label>
                <button disabled={create.isPending} onClick={() => create.mutate()}>
                    Create RMA
                </button>
            </fieldset>
            {rmaId && (
                <fieldset>
                    <legend>RMA {rmaId}</legend>
                    <button disabled={ship.isPending} onClick={() => ship.mutate()}>
                        Ship
                    </button>
                    <button disabled={closeR.isPending} onClick={() => closeR.mutate()}>
                        Close
                    </button>
                    {ship.isSuccess && <p role="status">Shipped.</p>}
                    {closeR.isSuccess && <p role="status">Closed.</p>}
                </fieldset>
            )}
        </section>
    );
}
