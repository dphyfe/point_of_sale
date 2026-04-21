"""Purchase Order state machine + role-pinning per FR-002 / FR-036."""

from __future__ import annotations

from dataclasses import dataclass

from pos_inventory.core.errors import BusinessRuleConflict, RoleForbidden

# Allowed transitions
TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted", "cancelled"},
    "submitted": {"approved", "cancelled"},
    "approved": {"sent", "cancelled"},
    "sent": {"receiving", "cancelled"},
    "receiving": {"closed"},
    "closed": set(),
    "cancelled": set(),
}

# Role pin per transition (any of these roles is sufficient; Admin is implicit).
ROLE_GATE: dict[tuple[str, str], frozenset[str]] = {
    ("draft", "submitted"): frozenset({"Purchasing"}),
    ("submitted", "approved"): frozenset({"Store Manager", "Purchasing"}),
    ("approved", "sent"): frozenset({"Purchasing"}),
    ("sent", "receiving"): frozenset({"Receiver", "Inventory Clerk"}),
    ("receiving", "closed"): frozenset({"Receiver", "Inventory Clerk", "Store Manager"}),
}


@dataclass(frozen=True)
class TransitionRequest:
    from_state: str
    to_state: str
    actor_roles: frozenset[str]


def assert_transition(req: TransitionRequest) -> None:
    if req.to_state not in TRANSITIONS.get(req.from_state, set()):
        raise BusinessRuleConflict(f"Illegal PO transition {req.from_state} -> {req.to_state}")
    needed = ROLE_GATE.get((req.from_state, req.to_state))
    if needed is None:
        return  # cancel from any state has no extra role pin
    if "Admin" in req.actor_roles:
        return
    if not (req.actor_roles & needed):
        raise RoleForbidden(f"transition requires one of {sorted(needed)}")
