import { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import { AuditTab } from './AuditTab';
import { ConsentTab } from './ConsentTab';
import { HistoryTab } from './HistoryTab';
import { MessagesTab } from './MessagesTab';

interface CustomerProfile {
    id: string;
    display_name: string;
    contact_type: 'individual' | 'company';
    email: string | null;
    primary_phone: string | null;
    state: 'active' | 'inactive' | 'merged' | 'anonymized';
    version: number;
    tags: string[];
    tax_id_masked: string | null;
    last_purchase_at: string | null;
    last_store_visited: string | null;
    lifetime_spend: string;
    visit_count: number;
    average_order_value: string;
}

type Tab = 'overview' | 'history' | 'messages' | 'consent' | 'audit';

export function CustomerProfilePage({ customerId }: { customerId: string }) {
    const [profile, setProfile] = useState<CustomerProfile | null>(null);
    const [tab, setTab] = useState<Tab>('overview');
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        api
            .get<CustomerProfile>(`/customers/${customerId}`)
            .then(setProfile)
            .catch((e) => setError((e as Error).message));
    }, [customerId]);

    if (error) return <p role="alert">{error}</p>;
    if (!profile) return <p>Loading…</p>;

    return (
        <article>
            <header>
                <h2>{profile.display_name}</h2>
                <p>
                    {profile.contact_type} · state: {profile.state} · v{profile.version}
                </p>
                <dl>
                    <dt>Lifetime spend</dt><dd>{profile.lifetime_spend}</dd>
                    <dt>Visits</dt><dd>{profile.visit_count}</dd>
                    <dt>AOV</dt><dd>{profile.average_order_value}</dd>
                    <dt>Last visit</dt>
                    <dd>{profile.last_purchase_at ? new Date(profile.last_purchase_at).toLocaleString() : '—'}</dd>
                </dl>
            </header>
            <nav>
                {(['overview', 'history', 'messages', 'consent', 'audit'] as Tab[]).map((t) => (
                    <button key={t} onClick={() => setTab(t)} disabled={tab === t}>
                        {t}
                    </button>
                ))}
            </nav>
            {tab === 'overview' && <OverviewTab profile={profile} onSaved={(p) => setProfile(p)} />}
            {tab === 'history' && <HistoryTab customerId={customerId} />}
            {tab === 'messages' && (
                <MessagesTab customerId={customerId} defaultEmail={profile.email ?? undefined} />
            )}
            {tab === 'consent' && <ConsentTab customerId={customerId} />}
            {tab === 'audit' && <AuditTab customerId={customerId} />}
        </article>
    );
}

function OverviewTab({
    profile,
    onSaved,
}: {
    profile: CustomerProfile;
    onSaved: (p: CustomerProfile) => void;
}) {
    const [draft, setDraft] = useState({
        first_name: '',
        last_name: '',
        email: profile.email ?? '',
        primary_phone: profile.primary_phone ?? '',
    });
    const [error, setError] = useState<string | null>(null);
    const [staleWarning, setStaleWarning] = useState(false);

    const save = async () => {
        setError(null);
        setStaleWarning(false);
        try {
            const updated = await api.put<CustomerProfile>(
                `/customers/${profile.id}`,
                {
                    contact_type: profile.contact_type,
                    ...draft,
                },
                { 'If-Match': String(profile.version) },
            );
            onSaved(updated);
        } catch (e) {
            const err = e as { code?: string; message?: string };
            if (err.code === 'stale_version') {
                setStaleWarning(true);
            } else {
                setError(err.message ?? 'save failed');
            }
        }
    };

    return (
        <section>
            <p>Email: <input value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })} /></p>
            <p>Phone: <input value={draft.primary_phone} onChange={(e) => setDraft({ ...draft, primary_phone: e.target.value })} /></p>
            <p>Tax ID: {profile.tax_id_masked ?? '—'}</p>
            <button onClick={save}>Save</button>
            {staleWarning && (
                <p role="alert">
                    Customer was updated by someone else.{' '}
                    <button onClick={() => window.location.reload()}>Reload latest</button>
                </p>
            )}
            {error && <p role="alert">{error}</p>}
        </section>
    );
}
