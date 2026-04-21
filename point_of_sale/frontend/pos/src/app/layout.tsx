import { Link } from "react-router-dom";
import type { PropsWithChildren } from "react";

const NAV: { to: string; label: string }[] = [
    { to: "/pos", label: "Purchase Orders" },
    { to: "/lookup/serial", label: "Serial Lookup" },
    { to: "/lookup/balance", label: "Inventory" },
    { to: "/returns", label: "Returns" },
    { to: "/counts", label: "Counts" },
    { to: "/transfers", label: "Transfers" },
];

export default function Layout({ children }: PropsWithChildren) {
    return (
        <div style={{ fontFamily: "system-ui", padding: "1rem" }}>
            <header style={{ borderBottom: "1px solid #ccc", paddingBottom: "0.5rem", marginBottom: "1rem" }}>
                <h1 style={{ display: "inline-block", marginRight: "1rem" }}>POS Inventory</h1>
                <nav style={{ display: "inline-flex", gap: "0.75rem" }}>
                    {NAV.map((n) => (
                        <Link key={n.to} to={n.to}>
                            {n.label}
                        </Link>
                    ))}
                </nav>
            </header>
            <main>{children}</main>
        </div>
    );
}
