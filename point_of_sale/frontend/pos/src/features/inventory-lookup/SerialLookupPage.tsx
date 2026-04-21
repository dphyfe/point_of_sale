import { useState } from 'react';
import { api } from '../../lib/api';

interface SerialHistoryEntry {
    occurred_at: string;
    source_kind: string;
    source_doc_id: string;
    location_id: string | null;
    qty_delta: string;
    unit_cost: string;
}
interface Serial {
    id: string;
    sku_id: string;
    serial_value: string;
    state: string;
    current_location_id: string | null;
    unit_cost: string;
    received_at: string;
}
interface SerialWithHistory {
    serial: Serial;
    history: SerialHistoryEntry[];
}

export function SerialLookupPage() {
    const [value, setValue] = useState('');
    const [data, setData] = useState<SerialWithHistory | null>(null);
    const [error, setError] = useState<string | null>(null);

    const search = async () => {
        setError(null);
        setData(null);
        try {
            const r = await api.get<SerialWithHistory>(`/serials/${encodeURIComponent(value)}`);
            setData(r);
        } catch (e) {
            setError((e as Error).message);
        }
    };

    return (
        <section>
            <h2>Serial Lookup</h2>
            <input
                aria-label="serial value"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && search()}
                placeholder="scan or type a serial"
            />
            <button onClick={search}>Lookup</button>
            {error && <p role="alert">{error}</p>}
            {data && (
                <div>
                    <h3>{data.serial.serial_value}</h3>
                    <p>
                        State: <strong>{data.serial.state}</strong>
                        {data.serial.current_location_id ? ` @ ${data.serial.current_location_id}` : ''}
                    </p>
                    <table>
                        <thead>
                            <tr>
                                <th>When</th>
                                <th>Source</th>
                                <th>Doc</th>
                                <th>Δ Qty</th>
                                <th>Unit Cost</th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.history.map((h, i) => (
                                <tr key={i}>
                                    <td>{new Date(h.occurred_at).toLocaleString()}</td>
                                    <td>{h.source_kind}</td>
                                    <td>{h.source_doc_id}</td>
                                    <td>{h.qty_delta}</td>
                                    <td>{h.unit_cost}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </section>
    );
}
