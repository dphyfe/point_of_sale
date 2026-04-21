import { getToken, getTenantId } from "./auth";

const BASE = (import.meta as { env?: { VITE_API_BASE?: string } }).env?.VITE_API_BASE ?? "/v1";

export type ApiError = { status: number; code: string; message: string; details?: unknown };

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { "content-type": "application/json" };
    const token = getToken();
    if (token) headers["authorization"] = `Bearer ${token}`;
    const tid = getTenantId();
    if (tid) headers["x-tenant-id"] = tid;

    const r = await fetch(`${BASE}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!r.ok) {
        const payload = (await r.json().catch(() => ({}))) as { code?: string; message?: string };
        const err: ApiError = {
            status: r.status,
            code: payload.code ?? `http_${r.status}`,
            message: payload.message ?? r.statusText,
        };
        throw err;
    }
    if (r.status === 204) return undefined as T;
    return (await r.json()) as T;
}

export const api = {
    get: <T>(p: string) => request<T>("GET", p),
    post: <T>(p: string, b?: unknown) => request<T>("POST", p, b),
    put: <T>(p: string, b?: unknown) => request<T>("PUT", p, b),
    del: <T>(p: string) => request<T>("DELETE", p),
};
