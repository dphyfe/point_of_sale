from __future__ import annotations

import re
from pathlib import Path


REVISION_RE = re.compile(r'^revision:\s*str\s*=\s*"([^"]+)"', re.MULTILINE)


def test_alembic_revision_ids_fit_default_version_table() -> None:
    versions_dir = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    revision_ids: list[tuple[str, int]] = []

    for migration_file in versions_dir.glob("*.py"):
        content = migration_file.read_text(encoding="utf-8")
        match = REVISION_RE.search(content)
        assert match is not None, f"Missing revision id in {migration_file.name}"
        revision_ids.append((match.group(1), len(match.group(1))))

    too_long = [
        f"{revision_id} ({length})"
        for revision_id, length in revision_ids
        if length > 32
    ]
    assert not too_long, "Alembic revision ids must be <= 32 chars: " + ", ".join(too_long)