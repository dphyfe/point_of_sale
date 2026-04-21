"""init schemas + RLS helper

Revision ID: 0001_init_schemas
Revises:
Create Date: 2026-04-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_init_schemas"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMAS = ["inv", "po", "ret", "rma", "cnt", "xfr", "audit", "outbox"]


def upgrade() -> None:
    for s in SCHEMAS:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{s}"')

    # RLS helper: returns the per-request tenant guc as uuid (NULL when unset).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_current_tenant() RETURNS uuid
        LANGUAGE sql STABLE AS $$
            SELECT NULLIF(current_setting('app.current_tenant', true), '')::uuid
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_current_tenant()")
    for s in reversed(SCHEMAS):
        op.execute(f'DROP SCHEMA IF EXISTS "{s}" CASCADE')
