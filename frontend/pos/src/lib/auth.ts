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

// Dev-mode (POS_INVENTORY_AUTH_BYPASS=true on the backend) fallback keys.
// When no JWT is set, api.ts sends X-Dev-Tenant/X-Dev-User/X-Dev-Roles built
// from these (or the defaults below) so the local stack works out of the box.
const DEV_TENANT_KEY = "pos_dev_tenant";
const DEV_USER_KEY = "pos_dev_user";
const DEV_ROLES_KEY = "pos_dev_roles";

export const DEFAULT_DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001";
export const DEFAULT_DEV_USER_ID = "00000000-0000-0000-0000-000000000002";
export const DEFAULT_DEV_ROLES: Role[] = ["Admin"];

export function getDevTenantId(): string {
    return localStorage.getItem(DEV_TENANT_KEY) ?? DEFAULT_DEV_TENANT_ID;
}

export function getDevUserId(): string {
    return localStorage.getItem(DEV_USER_KEY) ?? DEFAULT_DEV_USER_ID;
}

export function getDevRoles(): Role[] {
    const raw = localStorage.getItem(DEV_ROLES_KEY);
    if (!raw) return DEFAULT_DEV_ROLES;
    try {
        const parsed = JSON.parse(raw) as Role[];
        return Array.isArray(parsed) && parsed.length > 0 ? parsed : DEFAULT_DEV_ROLES;
    } catch {
        return DEFAULT_DEV_ROLES;
    }
}

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
    if (!raw) {
        // No real session — fall back to dev roles so role-gated UI works
        // against a backend running with POS_INVENTORY_AUTH_BYPASS=true.
        return getDevRoles();
    }
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
