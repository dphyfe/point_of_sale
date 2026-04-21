import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../lib/api';

type ContactType = 'individual' | 'company';
type CustomerState = 'active' | 'inactive' | 'merged' | 'anonymized';

interface CustomerSummary {
    id: string;
    contact_type: ContactType;
    display_name: string;
    email: string | null;
    primary_phone: string | null;
    state: CustomerState;
    tags: string[];
}

interface SearchResponse {
    items: CustomerSummary[];
    total: number;
    limit: number;
    offset: number;
}

export function CustomerSearchPage() {
    const [q, setQ] = useState('');
    const [includeInactive, setIncludeInactive] = useState(false);

    const query = useQuery({
        queryKey: ['customers', q.trim(), includeInactive],
        queryFn: () => {
            const params = new URLSearchParams();
            if (q.trim()) params.set('q', q.trim());
            params.set('include_inactive', String(includeInactive));
            return api.get<SearchResponse>(`/customers?${params.toString()}`);
        },
    });

    const data = query.data;
    const isSearching = q.trim().length > 0;

    return (
        <section>
            <h2>Customers</h2>
            <input
                aria-label="customer search"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Phone, email, name, or loyalty ID"
            />
            <label>
                <input
                    type="checkbox"
                    checked={includeInactive}
                    onChange={(e) => setIncludeInactive(e.target.checked)}
                />
                Include inactive
            </label>
            <button onClick={() => query.refetch()} disabled={query.isFetching}>
                {query.isFetching ? 'Loading…' : 'Refresh'}
            </button>
            {query.error && <p role="alert">{(query.error as Error).message}</p>}
            {data && (
                <div>
                    <h3>
                        {isSearching
                            ? `Search results (${data.total})`
                            : `Recent customers (${data.total})`}
                    </h3>
                    {data.items.length === 0 ? (
                        <p>No customers found.</p>
                    ) : (
                        <table>
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>Type</th>
                                    <th>Email</th>
                                    <th>Phone</th>
                                    <th>State</th>
                                    <th>Tags</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data.items.map((c) => (
                                    <tr key={c.id}>
                                        <td>
                                            <Link to={`/customers/${c.id}`}>{c.display_name}</Link>
                                        </td>
                                        <td>{c.contact_type}</td>
                                        <td>{c.email ?? ''}</td>
                                        <td>{c.primary_phone ?? ''}</td>
                                        <td>{c.state}</td>
                                        <td>{c.tags.join(', ')}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            )}
        </section>
    );
}
