import { useEffect, useState } from 'react';
import { api } from '../../lib/api';

interface MatrixRow {
    channel: string;
    purpose: string;
    state: string;
    updated_at: string;
}

interface HistoryRow {
    id: string;
    channel: string;
    purpose: string;
    event_kind: string;
    source: string;
    actor_user_id: string | null;
    occurred_at: string;
    note: string | null;
}

interface ConsentResponse {
    matrix: MatrixRow[];
    history: HistoryRow[];
}

const CHANNELS = ['email', 'sms'] as const;
const PURPOSES = ['transactional', 'marketing'] as const;

export function ConsentTab({ customerId }: { customerId: string }) {
    const [data, setData] = useState<ConsentResponse | null>(null);
    const [error, setError] = useState<string | null>(null);

    const load = () =>
        api
            .get<ConsentResponse>(`/customers/${customerId}/consent`)
            .then(setData)
            .catch((e) => setError((e as Error).message));
    useEffect(load, [customerId]);

    const update = async (channel: string, purpose: string, kind: 'opt_in' | 'opt_out') => {
        await api.post(`/customers/${customerId}/consent`, {
            channel,
            purpose,
            event_kind: kind,
            source: 'pos',
        });
        load();
    };

    if (error) return <p role="alert">{error}</p>;
    if (!data) return <p>Loading…</p>;

    const lookup = (ch: string, pu: string) =>
        data.matrix.find((m) => m.channel === ch && m.purpose === pu)?.state ?? 'unset';

    return (
        <section>
            <h3>Consent matrix</h3>
            <table>
                <thead>
                    <tr>
                        <th>Channel</th>
                        <th>Purpose</th>
                        <th>State</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    {CHANNELS.flatMap((ch) =>
                        PURPOSES.map((pu) => (
                            <tr key={`${ch}:${pu}`}>
                                <td>{ch}</td>
                                <td>{pu}</td>
                                <td>{lookup(ch, pu)}</td>
                                <td>
                                    <button onClick={() => update(ch, pu, 'opt_in')}>Opt in</button>
                                    <button onClick={() => update(ch, pu, 'opt_out')}>
                                        Opt out
                                    </button>
                                </td>
                            </tr>
                        )),
                    )}
                </tbody>
            </table>

            <h3>History</h3>
            <table>
                <thead>
                    <tr>
                        <th>When</th>
                        <th>Channel</th>
                        <th>Purpose</th>
                        <th>Kind</th>
                        <th>Source</th>
                        <th>Note</th>
                    </tr>
                </thead>
                <tbody>
                    {data.history.map((h) => (
                        <tr key={h.id}>
                            <td>{new Date(h.occurred_at).toLocaleString()}</td>
                            <td>{h.channel}</td>
                            <td>{h.purpose}</td>
                            <td>{h.event_kind}</td>
                            <td>{h.source}</td>
                            <td>{h.note ?? ''}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </section>
    );
}
