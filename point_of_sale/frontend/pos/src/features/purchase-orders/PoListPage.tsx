import { Link } from 'react-router-dom';
import { usePurchaseOrders } from './usePurchaseOrders';

export function PoListPage() {
    const { data, isLoading, error } = usePurchaseOrders();
    if (isLoading) return <p>Loading…</p>;
    if (error) return <p>Failed to load purchase orders.</p>;
    return (
        <section>
            <header style={{ display: 'flex', justifyContent: 'space-between' }}>
                <h2>Purchase Orders</h2>
                <Link to="/pos/new">+ New PO</Link>
            </header>
            <table>
                <thead>
                    <tr>
                        <th>PO #</th>
                        <th>State</th>
                        <th>Total</th>
                        <th>Created</th>
                    </tr>
                </thead>
                <tbody>
                    {(data ?? []).map((po) => (
                        <tr key={po.id}>
                            <td>
                                <Link to={`/pos/${po.id}`}>{po.po_number}</Link>
                            </td>
                            <td>{po.state}</td>
                            <td>{po.expected_total}</td>
                            <td>{new Date(po.created_at).toLocaleString()}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </section>
    );
}
