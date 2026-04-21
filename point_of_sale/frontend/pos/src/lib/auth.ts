// Canonical roles per FR-036.
export type Role =
    | "Cashier"
    | "Receiver"
    | "Inventory Clerk"
    | "Store Manager"
    | "Purchasing"
    | "Admin";

const TOKEN_KEY = "pos_token";
const TENANT_KEY = "pos_tenant_id";
const ROLES_KEY = "pos_roles";

export function setSession(token: string, tenantId: string, roles: Role[]): void {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(TENANT_KEY, tenantId);
    localStorage.setItem(ROLES_KEY, JSON.stringify(roles));
}

export function clearSession(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(TENANT_KEY);
    localStorage.removeItem(ROLES_KEY);
}

export function getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY);
}

export function getTenantId(): string | null {
    return localStorage.getItem(TENANT_KEY);
}

export function getRoles(): Role[] {
    const raw = localStorage.getItem(ROLES_KEY);
    if (!raw) return [];
    try {
        return JSON.parse(raw) as Role[];
    } catch {
        return [];
    }
}

export function hasRole(...roles: Role[]): boolean {
    const owned = new Set(getRoles());
    if (owned.has("Admin")) return true;
    return roles.some((r) => owned.has(r));
}
