import { useMutation } from '@tanstack/react-query';
import { api } from '../../lib/api';

export interface ReceiptLineInput {
    po_line_id: string;
    received_qty: string;
    serial_values: string[];
    lot_code?: string | null;
}

export interface ReceiptInput {
    purchase_order_id: string;
    location_id: string;
    lines: ReceiptLineInput[];
}

export function useReceipt() {
    return useMutation({
        mutationFn: (body: ReceiptInput) => api.post<{ id: string }>('/receipts', body),
    });
}
