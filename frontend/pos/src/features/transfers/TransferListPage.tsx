import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api } from '../../lib/api';

interface Transfer {
    id: string;
    state: string;
    source_location_id: string;
    destination_location_id: string;
    created_at: string;
}

export function TransferListPage() {
    const q = useQuery({
        queryKey: ['transfers'],
        queryFn: () => api.get<Transfer[]>('/transfers'),
    });
    return (
        <section>
            <h2>Transfers</h2>
            <Link to="/transfers/new">+ New</Link>
            {q.isLoading && <p>Loading…</p>}
            <ul>
                {q.data?.map((t) => (
                    <li key={t.id}>
                        <Link to={`/transfers/${t.id}`}>
                            {t.id.slice(0, 8)} — {t.state}
                        </Link>
                    </li>
                ))}
            </ul>
        </section>
    );
}
