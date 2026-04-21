import { Link } from 'react-router-dom';
import { usePurchaseOrders } from './usePurchaseOrders';

const PILL_BY_STATE: Record<string, string> = {
    draft: 'pill',
    submitted: 'pill pill-info',
    approved: 'pill pill-info',
    sent: 'pill pill-warning',
    receiving: 'pill pill-warning',
    closed: 'pill pill-success',
    cancelled: 'pill pill-danger',
};

const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });

export function PoListPage() {
    const { data, isLoading, error } = usePurchaseOrders();
    return (
        <section>
            <div className="toolbar">
                <div className="toolbar__title">
                    <h2>Purchase Orders</h2>
                    {data && <span className="muted">{data.length} records</span>}
                </div>
                <div className="toolbar__actions">
                    <Link to="/pos/new" className="btn btn-primary">
                        + New PO
                    </Link>
                </div>
            </div>
            {isLoading && <p className="muted">Loading…</p>}
            {error && <p role="alert">Failed to load purchase orders.</p>}
            {!isLoading && !error && (
                <table>
                    <thead>
                        <tr>
                            <th>PO #</th>
                            <th>State</th>
                            <th className="num">Total</th>
                            <th>Created</th>
                        </tr>
                    </thead>
                    <tbody>
                        {(data ?? []).map((po) => (
                            <tr key={po.id}>
                                <td>
                                    <Link to={`/pos/${po.id}`}>{po.po_number}</Link>
                                </td>
                                <td>
                                    <span className={PILL_BY_STATE[po.state] ?? 'pill'}>{po.state}</span>
                                </td>
                                <td className="num">{currency.format(Number(po.expected_total))}</td>
                                <td>{new Date(po.created_at).toLocaleString()}</td>
                            </tr>
                        ))}
                        {(data ?? []).length === 0 && (
                            <tr>
                                <td colSpan={4} className="muted" style={{ textAlign: 'center', padding: 24 }}>
                                    No purchase orders yet.
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            )}
        </section>
    );
}
