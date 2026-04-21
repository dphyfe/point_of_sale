import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ReceivePage } from '../ReceivePage';

// Mock data hooks so we don't need a real backend.
vi.mock('../../purchase-orders/usePurchaseOrders', () => ({
    usePurchaseOrder: () => ({
        data: {
            id: 'po-1',
            vendor_id: 'v',
            po_number: 'PO-1',
            state: 'sent',
            expected_total: '0',
            created_at: new Date().toISOString(),
            lines: [
                {
                    id: 'pol-1',
                    sku_id: 'sku-phone',
                    ordered_qty: '2',
                    received_qty: '0',
                    backordered_qty: '2',
                    unit_cost: '100',
                },
            ],
        },
        isLoading: false,
    }),
}));

const mutateAsync = vi.fn().mockResolvedValue({ id: 'r-1' });
vi.mock('../useReceipt', () => ({
    useReceipt: () => ({ mutateAsync, isPending: false }),
}));

function renderUI() {
    const qc = new QueryClient();
    return render(
        <QueryClientProvider client={qc}>
            <MemoryRouter initialEntries={['/receive/po-1']}>
                <Routes>
                    <Route path="/receive/:poId" element={<ReceivePage />} />
                </Routes>
            </MemoryRouter>
        </QueryClientProvider>,
    );
}

describe('ReceivePage serial scan guard', () => {
    beforeEach(() => mutateAsync.mockClear());

    it('blocks submit when serial count != received qty', async () => {
        renderUI();
        fireEvent.change(screen.getByRole('textbox', { name: /destination location/i }), {
            target: { value: 'loc-1' },
        });
        // Mark line as serialized; receive 2; only scan 1 serial.
        const checkboxes = screen.getAllByRole('checkbox');
        fireEvent.click(checkboxes[0]); // serial
        fireEvent.change(screen.getAllByRole('spinbutton')[0], { target: { value: '2' } });
        const scanInput = screen.getByLabelText(/scan serial/i);
        fireEvent.change(scanInput, { target: { value: 'SN-1' } });
        fireEvent.keyDown(scanInput, { key: 'Enter' });

        fireEvent.click(screen.getByRole('button', { name: /post receipt/i }));
        await waitFor(() => {
            expect(screen.getByRole('alert')).toHaveTextContent(/serial count must equal received qty/i);
        });
        expect(mutateAsync).not.toHaveBeenCalled();
    });

    it('submits when serial count matches received qty', async () => {
        renderUI();
        fireEvent.change(screen.getByRole('textbox', { name: /destination location/i }), {
            target: { value: 'loc-1' },
        });
        fireEvent.click(screen.getAllByRole('checkbox')[0]);
        fireEvent.change(screen.getAllByRole('spinbutton')[0], { target: { value: '2' } });
        const scan = screen.getByLabelText(/scan serial/i);
        fireEvent.change(scan, { target: { value: 'SN-1' } });
        fireEvent.keyDown(scan, { key: 'Enter' });
        fireEvent.change(scan, { target: { value: 'SN-2' } });
        fireEvent.keyDown(scan, { key: 'Enter' });

        fireEvent.click(screen.getByRole('button', { name: /post receipt/i }));
        await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
        expect(mutateAsync.mock.calls[0][0].lines[0].serial_values).toEqual(['SN-1', 'SN-2']);
    });
});
