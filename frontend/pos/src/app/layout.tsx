import { NavLink } from "react-router-dom";
import type { PropsWithChildren } from "react";

const NAV: { to: string; label: string }[] = [
    { to: "/pos", label: "Purchase Orders" },
    { to: "/lookup/serial", label: "Serial Lookup" },
    { to: "/lookup/balance", label: "Inventory" },
    { to: "/returns", label: "Returns" },
    { to: "/counts", label: "Counts" },
    { to: "/transfers", label: "Transfers" },
    { to: "/customers", label: "Customers" },
    { to: "/admin/templates", label: "Templates" },
];

export default function Layout({ children }: PropsWithChildren) {
    return (
        <div className="app-shell">
            <header className="app-header">
                <div className="app-header__brand">
                    <span className="app-header__brand-mark" aria-hidden>◆</span>
                    POS Inventory
                </div>
                <nav className="app-header__nav">
                    {NAV.map((n) => (
                        <NavLink
                            key={n.to}
                            to={n.to}
                            className={({ isActive }) => (isActive ? "is-active" : undefined)}
                        >
                            {n.label}
                        </NavLink>
                    ))}
                </nav>
                <div className="app-header__right">
                    <span>Dev Tenant</span>
                    <span className="app-header__avatar" aria-hidden>D</span>
                </div>
            </header>
            <main className="app-main">{children}</main>
        </div>
    );
}
