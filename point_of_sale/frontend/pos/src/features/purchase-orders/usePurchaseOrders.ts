import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../lib/api';

export interface PoLineInput {
    sku_id: string;
    ordered_qty: string;
    unit_cost: string;
}

export interface PoInput {
    vendor_id: string;
    po_number: string;
    lines: PoLineInput[];
}

export interface PoLine {
    id: string;
    sku_id: string;
    ordered_qty: string;
    received_qty: string;
    backordered_qty: string;
    unit_cost: string;
}

export interface PurchaseOrder {
    id: string;
    vendor_id: string;
    po_number: string;
    state: string;
    expected_total: string;
    created_at: string;
    lines: PoLine[];
}

export function usePurchaseOrders(state?: string) {
    const qs = state ? `?state=${encodeURIComponent(state)}` : '';
    return useQuery<PurchaseOrder[]>({
        queryKey: ['purchase-orders', state ?? 'all'],
        queryFn: () => api.get<PurchaseOrder[]>(`/purchase-orders${qs}`),
    });
}

export function usePurchaseOrder(id: string | undefined) {
    return useQuery<PurchaseOrder>({
        queryKey: ['purchase-orders', id],
        enabled: !!id,
        queryFn: () => api.get<PurchaseOrder>(`/purchase-orders/${id}`),
    });
}

export function useCreatePurchaseOrder() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (body: PoInput) => api.post<{ id: string }>('/purchase-orders', body),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['purchase-orders'] }),
    });
}

export function useTransitionPo() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: ({ id, action }: { id: string; action: 'submit' | 'approve' | 'send' | 'cancel' }) =>
            api.post<{ id: string; state: string }>(`/purchase-orders/${id}/${action}`, {}),
        onSuccess: (_d, vars) => {
            qc.invalidateQueries({ queryKey: ['purchase-orders'] });
            qc.invalidateQueries({ queryKey: ['purchase-orders', vars.id] });
        },
    });
}
