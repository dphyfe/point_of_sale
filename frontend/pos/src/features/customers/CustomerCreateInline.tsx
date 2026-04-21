import { useState } from 'react';
import { api } from '../../lib/api';

interface NewCustomer {
    contact_type: 'individual' | 'company';
    first_name?: string;
    last_name?: string;
    company_name?: string;
    email?: string;
    primary_phone?: string;
}

export function CustomerCreateInline({
    onCreated,
}: {
    onCreated: (id: string) => void;
}) {
    const [draft, setDraft] = useState<NewCustomer>({ contact_type: 'individual' });
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const submit = async () => {
        setError(null);
        setBusy(true);
        try {
            const body: Record<string, unknown> = {
                ...draft,
                client_request_id: crypto.randomUUID(),
            };
            const created = await api.post<{ id: string }>(`/customers`, body);
            onCreated(created.id);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    return (
        <fieldset>
            <legend>New customer</legend>
            <select
                value={draft.contact_type}
                onChange={(e) =>
                    setDraft({ ...draft, contact_type: e.target.value as 'individual' | 'company' })
                }
            >
                <option value="individual">Individual</option>
                <option value="company">Company</option>
            </select>
            {draft.contact_type === 'company' ? (
                <input
                    placeholder="Company name"
                    value={draft.company_name ?? ''}
                    onChange={(e) => setDraft({ ...draft, company_name: e.target.value })}
                />
            ) : (
                <>
                    <input
                        placeholder="First"
                        value={draft.first_name ?? ''}
                        onChange={(e) => setDraft({ ...draft, first_name: e.target.value })}
                    />
                    <input
                        placeholder="Last"
                        value={draft.last_name ?? ''}
                        onChange={(e) => setDraft({ ...draft, last_name: e.target.value })}
                    />
                </>
            )}
            <input
                placeholder="Email"
                value={draft.email ?? ''}
                onChange={(e) => setDraft({ ...draft, email: e.target.value })}
            />
            <input
                placeholder="Phone"
                value={draft.primary_phone ?? ''}
                onChange={(e) => setDraft({ ...draft, primary_phone: e.target.value })}
            />
            {error && <p role="alert">{error}</p>}
            <button onClick={submit} disabled={busy}>
                Create
            </button>
        </fieldset>
    );
}
