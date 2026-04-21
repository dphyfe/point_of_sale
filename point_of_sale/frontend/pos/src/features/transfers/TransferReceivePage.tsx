import { useMutation } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { api } from '../../lib/api';

export function TransferReceivePage() {
    const { id } = useParams();
    const recv = useMutation({ mutationFn: () => api.post(`/transfers/${id}/receive`, {}) });
    return (
        <section>
            <h2>Receive Transfer {id?.slice(0, 8)}</h2>
            <p>Posts outbound from virtual_in_transit + inbound to destination.</p>
            <button disabled={recv.isPending} onClick={() => recv.mutate()}>
                Confirm Receive
            </button>
            {recv.isSuccess && <p role="status">Received.</p>}
            {recv.error && <p role="alert">{(recv.error as Error).message}</p>}
        </section>
    );
}
