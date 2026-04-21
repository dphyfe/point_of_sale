export const REASON_CODES = ['defective', 'wrong_item', 'changed_mind', 'damaged_in_transit', 'other'] as const;
export const DISPOSITIONS = ['sellable', 'hold', 'scrap', 'vendor_rma'] as const;

export function ReasonAndDispositionPicker({
    reason,
    disposition,
    onChange,
}: {
    reason: string;
    disposition: string;
    onChange: (patch: { reason?: string; disposition?: string }) => void;
}) {
    return (
        <span>
            <select aria-label="reason" value={reason} onChange={(e) => onChange({ reason: e.target.value })}>
                <option value="">— reason —</option>
                {REASON_CODES.map((r) => (
                    <option key={r} value={r}>
                        {r}
                    </option>
                ))}
            </select>
            <select
                aria-label="disposition"
                value={disposition}
                onChange={(e) => onChange({ disposition: e.target.value })}
            >
                <option value="">— disposition —</option>
                {DISPOSITIONS.map((d) => (
                    <option key={d} value={d}>
                        {d}
                    </option>
                ))}
            </select>
        </span>
    );
}
