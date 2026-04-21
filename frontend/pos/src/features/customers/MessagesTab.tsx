import { useEffect, useState } from 'react';
import { api } from '../../lib/api';

interface Message {
    id: string;
    channel: string;
    purpose: string;
    to_address: string;
    subject: string | null;
    body: string;
    status: string;
    provider: string | null;
    provider_message_id: string | null;
    created_at: string;
    updated_at: string;
}

export function MessagesTab({
    customerId,
    defaultEmail,
}: {
    customerId: string;
    defaultEmail?: string | null;
}) {
    const [items, setItems] = useState<Message[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [draft, setDraft] = useState({
        template_code: '',
        channel: 'email' as 'email' | 'sms',
        purpose: 'transactional' as 'transactional' | 'marketing',
        to_address: defaultEmail ?? '',
        free_text_subject: '',
        free_text_body: '',
    });
    const [sending, setSending] = useState(false);

    const load = () => {
        api
            .get<{ items: Message[] }>(`/customers/${customerId}/messages`)
            .then((r) => setItems(r.items))
            .catch((e) => setError((e as Error).message));
    };
    useEffect(load, [customerId]);

    const send = async () => {
        setError(null);
        setSending(true);
        try {
            await api.post(`/customers/${customerId}/messages`, {
                ...draft,
                template_code: draft.template_code || null,
                free_text_subject: draft.free_text_subject || null,
                free_text_body: draft.free_text_body || null,
                client_request_id: crypto.randomUUID(),
            });
            load();
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setSending(false);
        }
    };

    const retry = async (id: string) => {
        await api.post(`/customer-messages/${id}/retry`, {});
        load();
    };

    const smsCounter = draft.channel === 'sms' ? `${draft.free_text_body.length}/160` : null;

    if (error) return <p role="alert">{error}</p>;

    return (
        <section>
            <fieldset>
                <legend>Send message</legend>
                <input
                    placeholder="template_code (optional)"
                    value={draft.template_code}
                    onChange={(e) => setDraft({ ...draft, template_code: e.target.value })}
                />
                <select
                    value={draft.channel}
                    onChange={(e) =>
                        setDraft({ ...draft, channel: e.target.value as 'email' | 'sms' })
                    }
                >
                    <option value="email">email</option>
                    <option value="sms">sms</option>
                </select>
                <select
                    value={draft.purpose}
                    onChange={(e) =>
                        setDraft({
                            ...draft,
                            purpose: e.target.value as 'transactional' | 'marketing',
                        })
                    }
                >
                    <option value="transactional">transactional</option>
                    <option value="marketing">marketing</option>
                </select>
                <input
                    placeholder="to_address"
                    value={draft.to_address}
                    onChange={(e) => setDraft({ ...draft, to_address: e.target.value })}
                />
                {draft.channel === 'email' && (
                    <input
                        placeholder="Subject"
                        value={draft.free_text_subject}
                        onChange={(e) => setDraft({ ...draft, free_text_subject: e.target.value })}
                    />
                )}
                <textarea
                    placeholder="Body (or omit if using template_code)"
                    value={draft.free_text_body}
                    onChange={(e) => setDraft({ ...draft, free_text_body: e.target.value })}
                />
                {smsCounter && <span>{smsCounter}</span>}
                <button onClick={send} disabled={sending}>
                    Send
                </button>
            </fieldset>

            {!items ? (
                <p>Loading…</p>
            ) : (
                <table>
                    <thead>
                        <tr>
                            <th>When</th>
                            <th>Channel</th>
                            <th>To</th>
                            <th>Subject</th>
                            <th>Status</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        {items.map((m) => (
                            <tr key={m.id}>
                                <td>{new Date(m.created_at).toLocaleString()}</td>
                                <td>{m.channel}</td>
                                <td>{m.to_address}</td>
                                <td>{m.subject ?? ''}</td>
                                <td>{m.status}</td>
                                <td>
                                    {(m.status === 'failed' || m.status === 'bounced') && (
                                        <button onClick={() => retry(m.id)}>Retry</button>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </section>
    );
}
