import { useEffect, useState } from 'react';
import { api } from '../../lib/api';

interface AuditEntry {
    id: string;
    occurred_at: string;
    actor_user_id: string | null;
    field: string;
    old_value: string | null;
    new_value: string | null;
    change_kind: string;
}

export function AuditTab({ customerId }: { customerId: string }) {
    const [items, setItems] = useState<AuditEntry[] | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        api
            .get<{ items: AuditEntry[] }>(`/customers/${customerId}/audit`)
            .then((r) => setItems(r.items))
            .catch((e) => setError((e as Error).message));
    }, [customerId]);

    if (error) return <p role="alert">{error}</p>;
    if (!items) return <p>Loading…</p>;

    return (
        <table>
            <thead>
                <tr>
                    <th>When</th>
                    <th>Field</th>
                    <th>Kind</th>
                    <th>Old</th>
                    <th>New</th>
                    <th>Actor</th>
                </tr>
            </thead>
            <tbody>
                {items.map((it) => (
                    <tr key={it.id}>
                        <td>{new Date(it.occurred_at).toLocaleString()}</td>
                        <td>{it.field}</td>
                        <td>{it.change_kind}</td>
                        <td>{it.old_value ?? ''}</td>
                        <td>{it.new_value ?? ''}</td>
                        <td>{it.actor_user_id ?? ''}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}
