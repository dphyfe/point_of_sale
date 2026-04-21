import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api } from '../../lib/api';
import { hasRole } from '../../lib/auth';
import { ReasonAndDispositionPicker } from './ReasonAndDispositionPicker';

interface DraftLine {
    sku_id: string;
    qty: string;
    reason_code: string;
    disposition: string;
    target_location_id: string;
    serial_value?: string;
    refund_amount: string;
}

const blank: DraftLine = {
    sku_id: '',
    qty: '1',
    reason_code: '',
    disposition: '',
    target_location_id: '',
    serial_value: '',
    refund_amount: '0',
};

export function ReturnPage() {
    const [originalSaleId, setOriginalSaleId] = useState('');
    const [noReceipt, setNoReceipt] = useState(false);
    const [managerId, setManagerId] = useState('');
    const [cashierId, setCashierId] = useState('');
    const [lines, setLines] = useState<DraftLine[]>([{ ...blank }]);
    const refundMethod = noReceipt ? 'store_credit' : 'original';

    const submit = useMutation({
        mutationFn: () =>
            api.post<{ id: string }>('/returns', {
                cashier_user_id: cashierId,
                original_sale_id: originalSaleId || null,
                no_receipt: noReceipt,
                manager_approval_user_id: noReceipt ? managerId : null,
                refund_method: refundMethod,
                lines,
            }),
    });

    const setLine = (i: number, patch: Partial<DraftLine>) =>
        setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));

    const noReceiptDisabledByRole = noReceipt && !hasRole('Store Manager') && !hasRole('Admin');

    return (
        <section>
            <h2>Customer Return</h2>
            <label>
                Cashier user id
                <input value={cashierId} onChange={(e) => setCashierId(e.target.value)} />
            </label>
            <label>
                <input
                    type="checkbox"
                    checked={noReceipt}
                    onChange={(e) => setNoReceipt(e.target.checked)}
                />
                No receipt (manager approval required, refund forced to store credit)
            </label>
            {!noReceipt && (
                <label>
                    Original sale id
                    <input value={originalSaleId} onChange={(e) => setOriginalSaleId(e.target.value)} />
                </label>
            )}
            {noReceipt && (
                <label>
                    Manager approval user id
                    <input value={managerId} onChange={(e) => setManagerId(e.target.value)} />
                </label>
            )}
            <p>
                Refund method: <strong>{refundMethod}</strong>
            </p>

            <table>
                <thead>
                    <tr>
                        <th>SKU</th>
                        <th>Qty</th>
                        <th>Serial</th>
                        <th>Reason / Disposition</th>
                        <th>Target Location</th>
                        <th>Refund Amount</th>
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
                                    placeholder="optional"
                                    value={l.serial_value}
                                    onChange={(e) => setLine(i, { serial_value: e.target.value })}
                                />
                            </td>
                            <td>
                                <ReasonAndDispositionPicker
                                    reason={l.reason_code}
                                    disposition={l.disposition}
                                    onChange={(p) =>
                                        setLine(i, {
                                            reason_code: p.reason ?? l.reason_code,
                                            disposition: p.disposition ?? l.disposition,
                                        })
                                    }
                                />
                            </td>
                            <td>
                                <input
                                    value={l.target_location_id}
                                    onChange={(e) => setLine(i, { target_location_id: e.target.value })}
                                />
                            </td>
                            <td>
                                <input
                                    type="number"
                                    value={l.refund_amount}
                                    onChange={(e) => setLine(i, { refund_amount: e.target.value })}
                                />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
            <button onClick={() => setLines((ls) => [...ls, { ...blank }])}>+ Line</button>
            <button
                disabled={submit.isPending || noReceiptDisabledByRole}
                onClick={() => submit.mutate()}
            >
                Post Return
            </button>
            {noReceiptDisabledByRole && (
                <p role="alert">No-receipt returns require Store Manager role.</p>
            )}
            {submit.isSuccess && <p role="status">Return {submit.data.id} posted.</p>}
            {submit.error && <p role="alert">{(submit.error as Error).message}</p>}
        </section>
    );
}
