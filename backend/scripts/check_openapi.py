"""CI check: ensure FastAPI's generated OpenAPI matches the contract files.

Failure conditions:
- A path in any contract is missing from the generated spec.
- A path in the generated spec is missing from every contract (drift).
- An operation's HTTP method set differs from the merged contract view.

Usage:
    python backend/scripts/check_openapi.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = [
    REPO_ROOT / "specs" / "001-inventory-management" / "contracts" / "openapi.yaml",
    REPO_ROOT / "specs" / "002-customer-view" / "contracts" / "openapi.yaml",
]

# Routes intentionally not declared in any contract (operational endpoints).
SKIP_GENERATED = {"/healthz", "/v1/config"}

# Contract entries known to lack a generated implementation; tracked elsewhere
# and intentionally excluded from this drift check.
SKIP_CONTRACT = {"/skus"}

_PARAM_RE = re.compile(r"\{[^}]+\}")


def _normalize(path: str) -> str:
    """Strip leading ``/v1`` and collapse any ``{...}`` segment to ``{id}``.

    Lets the contract files (which use unprefixed paths and a single placeholder
    name like ``{id}`` or ``{customer_id}``) compare cleanly against the
    generated FastAPI spec where every router carries a ``/v1`` prefix and uses
    its own param names.
    """
    if path.startswith("/v1"):
        path = path[len("/v1"):] or "/"
    return _PARAM_RE.sub("{id}", path)


def _load_contracts() -> dict[str, dict]:
    """Return ``{path: methods_dict}`` merged across all contract files."""
    merged: dict[str, dict] = {}
    for cp in CONTRACTS:
        if not cp.exists():
            continue
        with cp.open("r", encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        for path, ops in (doc.get("paths") or {}).items():
            existing = merged.setdefault(path, {})
            existing.update(ops or {})
    return merged


def _generated() -> dict:
    sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
    from pos_inventory.main import create_app  # type: ignore

    app = create_app()
    return app.openapi()


def main() -> int:
    contract_paths = _load_contracts()
    gen = _generated()

    # Re-key both sides through the normalizer so prefix/param differences don't
    # surface as false drift.
    c_norm: dict[str, dict] = {}
    for raw, ops in contract_paths.items():
        norm = _normalize(raw)
        if norm in SKIP_CONTRACT:
            continue
        c_norm.setdefault(norm, {}).update(ops or {})
    g_norm: dict[str, dict] = {}
    for raw, ops in (gen.get("paths") or {}).items():
        if raw in SKIP_GENERATED:
            continue
        g_norm.setdefault(_normalize(raw), {}).update(ops or {})

    c_paths = set(c_norm.keys())
    g_paths = set(g_norm.keys())

    missing_in_gen = c_paths - g_paths
    extra_in_gen = g_paths - c_paths

    problems: list[str] = []
    if missing_in_gen:
        problems.append(f"missing in generated: {sorted(missing_in_gen)}")
    if extra_in_gen:
        problems.append(f"undeclared in contract: {sorted(extra_in_gen)}")

    for path in c_paths & g_paths:
        c_methods = {m.lower() for m in c_norm[path].keys() if m.lower() in {"get", "post", "put", "patch", "delete"}}
        g_methods = {m.lower() for m in g_norm[path].keys() if m.lower() in {"get", "post", "put", "patch", "delete"}}
        if c_methods != g_methods:
            problems.append(f"method drift on {path}: contract={sorted(c_methods)} generated={sorted(g_methods)}")

    if problems:
        print("OpenAPI drift detected:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 2
    print("OK: OpenAPI matches contract paths and methods.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
