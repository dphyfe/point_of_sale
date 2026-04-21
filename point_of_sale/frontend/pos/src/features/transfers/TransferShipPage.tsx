import { useMutation } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { api } from '../../lib/api';

export function TransferShipPage() {
    const { id } = useParams();
    const ship = useMutation({ mutationFn: () => api.post(`/transfers/${id}/ship`, {}) });
    return (
        <section>
            <h2>Ship Transfer {id?.slice(0, 8)}</h2>
            <p>
                Confirms the picked serials/qty match the draft and posts outbound from source +
                inbound to virtual_in_transit.
            </p>
            <button disabled={ship.isPending} onClick={() => ship.mutate()}>
                Confirm Ship
            </button>
            {ship.isSuccess && <p role="status">Shipped.</p>}
            {ship.error && <p role="alert">{(ship.error as Error).message}</p>}
        </section>
    );
}
