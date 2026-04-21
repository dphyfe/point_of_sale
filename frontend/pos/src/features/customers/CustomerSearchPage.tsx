import { useState } from 'react';
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
    const [data, setData] = useState<SearchResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    const search = async () => {
        setError(null);
        setLoading(true);
        try {
            const params = new URLSearchParams({ q, include_inactive: String(includeInactive) });
            const r = await api.get<SearchResponse>(`/customers?${params.toString()}`);
            setData(r);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <section>
            <h2>Customer Search</h2>
            <input
                aria-label="customer search"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && q.trim() && search()}
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
            <button onClick={search} disabled={!q.trim() || loading}>
                {loading ? 'Searching…' : 'Search'}
            </button>
            {error && <p role="alert">{error}</p>}
            {data && (
                <div>
                    <p>{data.total} result(s)</p>
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
                                    <td>{c.display_name}</td>
                                    <td>{c.contact_type}</td>
                                    <td>{c.email ?? ''}</td>
                                    <td>{c.primary_phone ?? ''}</td>
                                    <td>{c.state}</td>
                                    <td>{c.tags.join(', ')}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </section>
    );
}
