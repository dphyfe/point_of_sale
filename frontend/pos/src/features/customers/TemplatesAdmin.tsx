import { useEffect, useState } from 'react';
import { api } from '../../lib/api';

interface Template {
    id: string;
    code: string;
    name: string;
    channel: string;
    purpose: string;
    subject_template: string | null;
    body_template: string;
    enabled: boolean;
}

const EMPTY: Omit<Template, 'id'> = {
    code: '',
    name: '',
    channel: 'email',
    purpose: 'transactional',
    subject_template: '',
    body_template: '',
    enabled: true,
};

export function TemplatesAdmin() {
    const [items, setItems] = useState<Template[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [draft, setDraft] = useState<Omit<Template, 'id'>>(EMPTY);
    const [editingId, setEditingId] = useState<string | null>(null);

    const load = () =>
        api
            .get<{ items: Template[] }>(`/message-templates`)
            .then((r) => setItems(r.items))
            .catch((e) => setError((e as Error).message));
    useEffect(load, []);

    const save = async () => {
        try {
            const body = {
                ...draft,
                subject_template: draft.subject_template || null,
            };
            if (editingId) await api.put(`/message-templates/${editingId}`, body);
            else await api.post(`/message-templates`, body);
            setDraft(EMPTY);
            setEditingId(null);
            load();
        } catch (e) {
            setError((e as Error).message);
        }
    };

    const startEdit = (t: Template) => {
        setEditingId(t.id);
        setDraft({
            code: t.code,
            name: t.name,
            channel: t.channel,
            purpose: t.purpose,
            subject_template: t.subject_template ?? '',
            body_template: t.body_template,
            enabled: t.enabled,
        });
    };

    if (error) return <p role="alert">{error}</p>;

    return (
        <section>
            <h2>Message Templates</h2>
            <fieldset>
                <legend>{editingId ? 'Edit template' : 'New template'}</legend>
                <input
                    placeholder="code"
                    value={draft.code}
                    disabled={!!editingId}
                    onChange={(e) => setDraft({ ...draft, code: e.target.value })}
                />
                <input
                    placeholder="name"
                    value={draft.name}
                    onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                />
                <select
                    value={draft.channel}
                    onChange={(e) => setDraft({ ...draft, channel: e.target.value })}
                >
                    <option value="email">email</option>
                    <option value="sms">sms</option>
                </select>
                <select
                    value={draft.purpose}
                    onChange={(e) => setDraft({ ...draft, purpose: e.target.value })}
                >
                    <option value="transactional">transactional</option>
                    <option value="marketing">marketing</option>
                </select>
                {draft.channel === 'email' && (
                    <input
                        placeholder="subject"
                        value={draft.subject_template ?? ''}
                        onChange={(e) =>
                            setDraft({ ...draft, subject_template: e.target.value })
                        }
                    />
                )}
                <textarea
                    placeholder="body"
                    value={draft.body_template}
                    onChange={(e) => setDraft({ ...draft, body_template: e.target.value })}
                />
                <label>
                    <input
                        type="checkbox"
                        checked={draft.enabled}
                        onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
                    />
                    enabled
                </label>
                <button onClick={save}>{editingId ? 'Save' : 'Create'}</button>
                {editingId && (
                    <button
                        onClick={() => {
                            setEditingId(null);
                            setDraft(EMPTY);
                        }}
                    >
                        Cancel
                    </button>
                )}
            </fieldset>
            {!items ? (
                <p>Loading…</p>
            ) : (
                <table>
                    <thead>
                        <tr>
                            <th>Code</th>
                            <th>Name</th>
                            <th>Channel</th>
                            <th>Purpose</th>
                            <th>Enabled</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        {items.map((t) => (
                            <tr key={t.id}>
                                <td>{t.code}</td>
                                <td>{t.name}</td>
                                <td>{t.channel}</td>
                                <td>{t.purpose}</td>
                                <td>{t.enabled ? 'yes' : 'no'}</td>
                                <td>
                                    <button onClick={() => startEdit(t)}>Edit</button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </section>
    );
}
