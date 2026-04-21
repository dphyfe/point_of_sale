import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api } from '../../lib/api';

interface Session {
    id: string;
    state: string;
    site_id: string;
    created_at: string;
    scope_kind: string;
}

export function CountSessionListPage() {
    const q = useQuery({
        queryKey: ['count-sessions'],
        queryFn: () => api.get<Session[]>('/count-sessions'),
    });
    return (
        <section>
            <h2>Count Sessions</h2>
            <Link to="/counts/new">+ New Session</Link>
            {q.isLoading && <p>Loading…</p>}
            {q.error && <p role="alert">{(q.error as Error).message}</p>}
            <ul>
                {q.data?.map((s) => (
                    <li key={s.id}>
                        <Link to={`/counts/${s.id}`}>
                            {s.id.slice(0, 8)} — {s.state} ({s.scope_kind})
                        </Link>
                    </li>
                ))}
            </ul>
        </section>
    );
}
