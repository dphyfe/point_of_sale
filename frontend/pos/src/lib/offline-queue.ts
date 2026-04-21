// IndexedDB-backed offline queue for non-serialized POS sales.
// Serialized sales are blocked while offline (FR-034).

import { api } from "./api";

const DB_NAME = "pos_offline";
const STORE = "pos_intake";
const DB_VERSION = 1;
const HEARTBEAT_KEY = "pos_last_online";

let _online = typeof navigator === "undefined" ? true : navigator.onLine;

export type SaleLine = {
    sku_id: string;
    qty: number;
    unit_price: string;
    serial_value?: never; // serialized lines may NOT be queued
};

export type PosSaleEnvelope = {
    client_intake_id: string;
    occurred_at: string;
    location_id: string;
    cashier_user_id: string;
    lines: SaleLine[];
};

function openDb(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_NAME, DB_VERSION);
        req.onupgradeneeded = () => {
            const db = req.result;
            if (!db.objectStoreNames.contains(STORE)) {
                db.createObjectStore(STORE, { keyPath: "client_intake_id" });
            }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

async function withStore<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => Promise<T> | T): Promise<T> {
    const db = await openDb();
    return new Promise<T>((resolve, reject) => {
        const tx = db.transaction(STORE, mode);
        const store = tx.objectStore(STORE);
        Promise.resolve(fn(store)).then(resolve).catch(reject);
        tx.oncomplete = () => db.close();
        tx.onerror = () => reject(tx.error);
    });
}

export async function enqueue(envelope: PosSaleEnvelope): Promise<void> {
    if (envelope.lines.some((l) => "serial_value" in l && (l as { serial_value?: string }).serial_value)) {
        throw new Error("serialized lines may not be queued offline");
    }
    await withStore("readwrite", (s) => {
        s.put(envelope);
    });
}

async function _all(): Promise<PosSaleEnvelope[]> {
    return withStore("readonly", (s) =>
        new Promise<PosSaleEnvelope[]>((resolve, reject) => {
            const req = s.getAll();
            req.onsuccess = () => resolve(req.result as PosSaleEnvelope[]);
            req.onerror = () => reject(req.error);
        }),
    );
}

async function _delete(key: string): Promise<void> {
    await withStore("readwrite", (s) => {
        s.delete(key);
    });
}

export async function drain(): Promise<{ posted: number; conflicts: number }> {
    const items = await _all();
    let posted = 0;
    let conflicts = 0;
    for (const it of items) {
        try {
            await api.post("/pos-intake/sales", { items: [it] });
            posted += 1;
        } catch (e) {
            const err = e as { status?: number; code?: string };
            if (err.status === 409 && err.code === "already_processed") {
                conflicts += 1;
            } else {
                // Stop draining on any non-409 error so we don't burn through retries.
                break;
            }
        }
        await _delete(it.client_intake_id);
    }
    return { posted, conflicts };
}

export function isOnline(): boolean {
    return _online;
}

export function markOnlineHeartbeat(): void {
    localStorage.setItem(HEARTBEAT_KEY, String(Date.now()));
}

export function startOnlineHeartbeat(intervalMs = 15_000): () => void {
    const tick = async () => {
        try {
            await fetch("/healthz", { method: "GET" });
            const wasOffline = !_online;
            _online = true;
            markOnlineHeartbeat();
            if (wasOffline) await drain();
        } catch {
            _online = false;
        }
    };
    if (typeof window !== "undefined") {
        window.addEventListener("online", () => {
            _online = true;
            void drain();
        });
        window.addEventListener("offline", () => {
            _online = false;
        });
    }
    void tick();
    const id = setInterval(tick, intervalMs) as unknown as number;
    return () => clearInterval(id);
}
