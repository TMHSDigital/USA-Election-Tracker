"""Loads sources/registry.yaml, the list of every external source we use."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .models import SourceRecord


def load_registry(repo_root: Path) -> dict[str, dict[str, Any]]:
    data = yaml.safe_load((repo_root / "sources" / "registry.yaml").read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for entry in data["sources"]:
        sid = entry["source_id"]
        if sid in out:
            raise ValueError(f"duplicate source_id {sid} in registry")
        out[sid] = entry
    return out


def source_record(
    registry: dict[str, dict[str, Any]],
    source_id: str,
    retrieved_at: datetime | None,
    source_published_at: datetime | None = None,
    url: str | None = None,
    notes: str | None = None,
) -> SourceRecord:
    """Build a SourceRecord for a registry entry, stamped with fetch times."""
    e = registry[source_id]
    if e.get("status") not in {"live", "partial"}:
        raise ValueError(f"source {source_id} is not usable (status={e.get('status')})")
    if e.get("redistribution") == "restricted":
        raise ValueError(f"source {source_id} does not allow redistribution")
    return SourceRecord(
        source_id=source_id,
        name=e["name"],
        publisher=e["publisher"],
        url=url or e["url"],
        license=e["license"],
        retrieved_at=retrieved_at,
        source_published_at=source_published_at,
        notes=notes if notes is not None else str(e.get("notes", "")).strip(),
    )
