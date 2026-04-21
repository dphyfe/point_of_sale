import { Link, useParams } from 'react-router-dom';
import { usePurchaseOrder, useTransitionPo } from './usePurchaseOrders';
import { hasRole } from '../../lib/auth';

export function PoDetailPage() {
    const { id } = useParams();
    const { data: po, isLoading } = usePurchaseOrder(id);
    const transition = useTransitionPo();

    if (isLoading || !po) return <p>Loading…</p>;
    const can = (action: 'submit' | 'approve' | 'send' | 'cancel'): boolean => {
        switch (action) {
            case 'submit':
                return po.state === 'draft' && hasRole('Purchasing');
            case 'approve':
                return po.state === 'submitted' && (hasRole('Store Manager') || hasRole('Purchasing'));
            case 'send':
                return po.state === 'approved' && hasRole('Purchasing');
            case 'cancel':
                return ['draft', 'submitted', 'approved', 'sent'].includes(po.state);
        }
    };
    return (
        <section>
            <h2>
                PO {po.po_number} <small>({po.state})</small>
            </h2>
            <div>
                {(['submit', 'approve', 'send', 'cancel'] as const).map((a) => (
                    <button
                        key={a}
                        disabled={!can(a) || transition.isPending}
                        onClick={() => transition.mutate({ id: po.id, action: a })}
                    >
                        {a}
                    </button>
                ))}
                {po.state === 'sent' || po.state === 'receiving' ? (
                    <Link to={`/receive/${po.id}`}>Receive</Link>
                ) : null}
            </div>
            <table>
                <thead>
                    <tr>
                        <th>SKU</th>
                        <th>Ordered</th>
                        <th>Received</th>
                        <th>Backordered</th>
                        <th>Unit Cost</th>
                    </tr>
                </thead>
                <tbody>
                    {po.lines.map((l) => (
                        <tr key={l.id}>
                            <td>{l.sku_id}</td>
                            <td>{l.ordered_qty}</td>
                            <td>{l.received_qty}</td>
                            <td>{l.backordered_qty}</td>
                            <td>{l.unit_cost}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </section>
    );
}
