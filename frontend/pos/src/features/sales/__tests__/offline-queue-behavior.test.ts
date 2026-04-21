import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import 'fake-indexeddb/auto';

import * as offline from '../../../lib/offline-queue';
import { api } from '../../../lib/api';
import { submitSale } from '../useSale';

describe('POS sale offline behavior', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });
    afterEach(async () => {
        // best-effort: reset the indexedDB by deleting db
        indexedDB.deleteDatabase('pos_offline');
    });

    it('blocks serialized line while offline', async () => {
        vi.spyOn(offline, 'isOnline').mockReturnValue(false);
        await expect(
            submitSale({
                client_intake_id: 'c1',
                occurred_at: new Date().toISOString(),
                location_id: 'loc-1',
                cashier_user_id: 'u-1',
                lines: [{ sku_id: 'sku-phone', qty: 1, unit_price: '100', serial_value: 'SN-1' }],
            }),
        ).rejects.toThrow(/offline/i);
    });

    it('enqueues non-serialized line while offline', async () => {
        vi.spyOn(offline, 'isOnline').mockReturnValue(false);
        const enqueueSpy = vi.spyOn(offline, 'enqueue').mockResolvedValue(undefined);
        const r = await submitSale({
            client_intake_id: 'c2',
            occurred_at: new Date().toISOString(),
            location_id: 'loc-1',
            cashier_user_id: 'u-1',
            lines: [{ sku_id: 'sku-mug', qty: 2, unit_price: '5' }],
        });
        expect(r.status).toBe('queued');
        expect(enqueueSpy).toHaveBeenCalledOnce();
    });

    it('online path POSTs to /pos-intake/sales', async () => {
        vi.spyOn(offline, 'isOnline').mockReturnValue(true);
        const postSpy = vi.spyOn(api, 'post').mockResolvedValue({} as never);
        const r = await submitSale({
            client_intake_id: 'c3',
            occurred_at: new Date().toISOString(),
            location_id: 'loc-1',
            cashier_user_id: 'u-1',
            lines: [{ sku_id: 'sku-mug', qty: 1, unit_price: '5' }],
        });
        expect(r.status).toBe('online');
        expect(postSpy).toHaveBeenCalledWith('/pos-intake/sales', expect.objectContaining({ items: expect.any(Array) }));
    });

    it('drain treats 409 already_processed as success', async () => {
        // enqueue one item, then mock api.post to throw a 409 already_processed
        await offline.enqueue({
            client_intake_id: 'c4',
            occurred_at: new Date().toISOString(),
            location_id: 'loc-1',
            cashier_user_id: 'u-1',
            lines: [{ sku_id: 'sku-mug', qty: 1, unit_price: '5' }],
        });
        vi.spyOn(api, 'post').mockRejectedValue({ status: 409, code: 'already_processed' });
        const res = await offline.drain();
        expect(res.conflicts).toBe(1);
        expect(res.posted).toBe(0);
    });
});
