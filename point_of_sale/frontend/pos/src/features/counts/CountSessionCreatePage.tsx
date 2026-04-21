import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '../../lib/api';

export function CountSessionCreatePage() {
    const navigate = useNavigate();
    const [siteId, setSiteId] = useState('');
    const [hideSystem, setHideSystem] = useState(true);
    const [locIds, setLocIds] = useState('');
    const [skuIds, setSkuIds] = useState('');

    const create = useMutation({
        mutationFn: () =>
            api.post<{ id: string }>('/count-sessions', {
                site_id: siteId,
                location_ids: locIds ? locIds.split(',').map((s) => s.trim()).filter(Boolean) : null,
                sku_ids: skuIds ? skuIds.split(',').map((s) => s.trim()).filter(Boolean) : null,
                hide_system_qty: hideSystem,
            }),
        onSuccess: (r) => navigate(`/counts/${r.id}`),
    });

    return (
        <section>
            <h2>New Count Session</h2>
            <label>
                Site id <input value={siteId} onChange={(e) => setSiteId(e.target.value)} />
            </label>
            <label>
                Location ids (comma sep, optional){' '}
                <input value={locIds} onChange={(e) => setLocIds(e.target.value)} />
            </label>
            <label>
                SKU ids (comma sep, optional){' '}
                <input value={skuIds} onChange={(e) => setSkuIds(e.target.value)} />
            </label>
            <label>
                <input
                    type="checkbox"
                    checked={hideSystem}
                    onChange={(e) => setHideSystem(e.target.checked)}
                />
                Hide system qty during counting (blind count)
            </label>
            <button disabled={create.isPending} onClick={() => create.mutate()}>
                Create
            </button>
            {create.error && <p role="alert">{(create.error as Error).message}</p>}
        </section>
    );
}
