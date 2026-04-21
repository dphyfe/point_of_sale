"""CI check: ensure FastAPI's generated OpenAPI matches the contract file.

Failure conditions:
- A path in the contract is missing from the generated spec.
- A path in the generated spec is missing from the contract (drift).
- An operation's HTTP method set differs.

Usage:
    python backend/scripts/check_openapi.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "specs" / "001-inventory-management" / "contracts" / "openapi.yaml"


def _load_contract() -> dict:
    with CONTRACT.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _generated() -> dict:
    sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
    from pos_inventory.main import create_app  # type: ignore

    app = create_app()
    return app.openapi()


def main() -> int:
    contract = _load_contract()
    gen = _generated()
    c_paths = set((contract.get("paths") or {}).keys())
    g_paths = set((gen.get("paths") or {}).keys())

    missing_in_gen = c_paths - g_paths
    extra_in_gen = g_paths - c_paths

    problems: list[str] = []
    if missing_in_gen:
        problems.append(f"missing in generated: {sorted(missing_in_gen)}")
    if extra_in_gen:
        problems.append(f"undeclared in contract: {sorted(extra_in_gen)}")

    for path in c_paths & g_paths:
        c_methods = {m.lower() for m in (contract["paths"][path] or {}).keys() if m.lower() in {"get", "post", "put", "patch", "delete"}}
        g_methods = {m.lower() for m in (gen["paths"][path] or {}).keys() if m.lower() in {"get", "post", "put", "patch", "delete"}}
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
