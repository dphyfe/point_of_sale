import { useEffect, useState } from 'react';
import { api } from '../../lib/api';

export interface InStockSerial {
    serial_value: string;
    current_location_id: string;
}

export function useInStockSerials(skuId: string, locationId: string) {
    const [data, setData] = useState<InStockSerial[]>([]);
    const [loading, setLoading] = useState(false);
    useEffect(() => {
        if (!skuId || !locationId) return;
        setLoading(true);
        api
            .get<InStockSerial[]>(
                `/inventory/serials?sku_id=${skuId}&location_id=${locationId}&state=sellable`,
            )
            .then(setData)
            .catch(() => setData([]))
            .finally(() => setLoading(false));
    }, [skuId, locationId]);
    return { data, loading };
}

export function SerialPicker({
    skuId,
    locationId,
    value,
    onChange,
}: {
    skuId: string;
    locationId: string;
    value: string;
    onChange: (v: string) => void;
}) {
    const { data, loading } = useInStockSerials(skuId, locationId);
    return (
        <div>
            <input
                list={`serials-${skuId}`}
                aria-label="serial value"
                placeholder="scan or pick serial"
                value={value}
                onChange={(e) => onChange(e.target.value)}
            />
            <datalist id={`serials-${skuId}`}>
                {data.map((s) => (
                    <option key={s.serial_value} value={s.serial_value} />
                ))}
            </datalist>
            {loading && <small> loading…</small>}
        </div>
    );
}
