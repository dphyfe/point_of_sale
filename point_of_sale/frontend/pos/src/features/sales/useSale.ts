import { useMutation } from '@tanstack/react-query';
import { api } from '../../lib/api';
import { enqueue, isOnline, type PosSaleEnvelope } from '../../lib/offline-queue';

export interface SaleLineInput {
    sku_id: string;
    qty: number;
    unit_price: string;
    serial_value?: string;
}

export interface SaleInput {
    client_intake_id: string;
    occurred_at: string;
    location_id: string;
    cashier_user_id: string;
    lines: SaleLineInput[];
}

/**
 * Drives a POS sale. Online: POSTs to /pos-intake/sales. Offline:
 * enqueues only non-serialized lines; serialized sales are blocked while
 * offline (FR-034).
 */
export async function submitSale(input: SaleInput): Promise<{ status: 'online' | 'queued' }> {
    const hasSerial = input.lines.some((l) => l.serial_value);
    if (!isOnline()) {
        if (hasSerial) {
            throw new Error('serialized SKUs cannot be sold while offline');
        }
        const envelope: PosSaleEnvelope = {
            client_intake_id: input.client_intake_id,
            occurred_at: input.occurred_at,
            location_id: input.location_id,
            cashier_user_id: input.cashier_user_id,
            lines: input.lines.map((l) => ({ sku_id: l.sku_id, qty: l.qty, unit_price: l.unit_price })),
        };
        await enqueue(envelope);
        return { status: 'queued' };
    }
    await api.post('/pos-intake/sales', { items: [input] });
    return { status: 'online' };
}

export function useSale() {
    return useMutation({ mutationFn: submitSale });
}
