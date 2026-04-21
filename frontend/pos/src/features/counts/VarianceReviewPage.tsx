import { useMutation, useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { api } from '../../lib/api';
import { hasRole } from '../../lib/auth';

interface VarianceLine {
    sku_id: string;
    location_id: string;
    system_at_open: string;
    delta_movements: string;
    counted_qty: string;
    variance_qty: string;
    variance_value: string;
}
interface VarianceReport {
    session_id: string;
    generated_at: string;
    lines: VarianceLine[];
}

export function VarianceReviewPage() {
    const { id } = useParams();
    const q = useQuery({
        queryKey: ['count-variance', id],
        queryFn: () => api.get<VarianceReport>(`/count-sessions/${id}/variance`),
        enabled: !!id,
    });
    const approve = useMutation({
        mutationFn: () => api.post(`/count-sessions/${id}/approve`, {}),
    });

    const canApprove = hasRole('Store Manager') || hasRole('Admin');

    return (
        <section>
            <h2>Variance Review — {id?.slice(0, 8)}</h2>
            {q.isLoading && <p>Loading…</p>}
            {q.error && <p role="alert">{(q.error as Error).message}</p>}
            <table>
                <thead>
                    <tr>
                        <th>SKU</th>
                        <th>Loc</th>
                        <th>Open</th>
                        <th>Δ during</th>
                        <th>Counted</th>
                        <th>Variance qty</th>
                        <th>Variance value</th>
                    </tr>
                </thead>
                <tbody>
                    {q.data?.lines.map((l, i) => (
                        <tr key={i}>
                            <td>{l.sku_id.slice(0, 8)}</td>
                            <td>{l.location_id.slice(0, 8)}</td>
                            <td>{l.system_at_open}</td>
                            <td>{l.delta_movements}</td>
                            <td>{l.counted_qty}</td>
                            <td>{l.variance_qty}</td>
                            <td>{l.variance_value}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
            <button disabled={!canApprove || approve.isPending} onClick={() => approve.mutate()}>
                Approve & Post Adjustments
            </button>
            {!canApprove && <p role="alert">Approval requires Store Manager.</p>}
            {approve.isSuccess && <p role="status">Approved.</p>}
        </section>
    );
}
