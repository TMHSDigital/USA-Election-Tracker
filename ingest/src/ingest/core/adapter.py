"""Common adapter interface: fetch -> validate -> normalize -> emit.

The runner calls each step inside a guard. If any step raises, the adapter's
previous output directory is left untouched (last good data) and the failure
is recorded in status.json. A failing source never aborts the whole run.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import shutil
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel

from .http import Http
from .models import SCHEMA_VERSION, SourceRecord

log = logging.getLogger(__name__)


class ValidationFailed(RuntimeError):
    """Raised by validate() when fetched data does not look like what we expect."""


@dataclass
class Context:
    http: Http
    repo_root: Path
    out_dir: Path
    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))
    work_dir: Path | None = None

    def scratch(self, name: str) -> Path:
        base = self.work_dir or (self.out_dir / ".work")
        p = base / name
        p.mkdir(parents=True, exist_ok=True)
        return p


@dataclass
class Dataset:
    tables: dict[str, list[BaseModel]]
    sources: list[SourceRecord]
    retrieved_at: datetime
    extra_files: dict[str, bytes] = field(default_factory=dict)


class Adapter(ABC):
    id: ClassVar[str]
    description: ClassVar[str] = ""
    # Experimental adapters (live results) only run when named explicitly.
    experimental: ClassVar[bool] = False
    # After this long without a successful run the UI shows a stale notice.
    max_age: ClassVar[timedelta] = timedelta(days=2)

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx

    @abstractmethod
    def fetch(self) -> Any: ...

    def validate(self, raw: Any) -> Any:
        return raw

    @abstractmethod
    def normalize(self, raw: Any) -> Dataset: ...

    def emit(self, ds: Dataset, out: Path) -> None:
        write_dataset(ds, out, adapter_id=self.id)


def write_dataset(ds: Dataset, out: Path, adapter_id: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    known = {s.source_id for s in ds.sources}
    counts: dict[str, int] = {}
    for name, rows in ds.tables.items():
        for row in rows:
            ids = getattr(row, "source_ids", None)
            if not ids:
                raise ValidationFailed(f"{adapter_id}.{name}: row without source_ids: {row}")
            missing = [i for i in ids if i not in known]
            if missing:
                raise ValidationFailed(f"{adapter_id}.{name}: unknown source_ids {missing}")
        dumped = [r.model_dump(mode="json") for r in rows]
        write_json(out / f"{name}.json", dumped)
        write_csv(out / f"{name}.csv", dumped)
        counts[name] = len(rows)
    for rel, content in ds.extra_files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    write_json(
        out / "_meta.json",
        {
            "adapter_id": adapter_id,
            "schema_version": SCHEMA_VERSION,
            "retrieved_at": ds.retrieved_at.isoformat(),
            "row_counts": counts,
            "sources": [s.model_dump(mode="json") for s in ds.sources],
        },
    )


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=False),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: _csv_cell(v) for k, v in r.items()})


def _csv_cell(v: Any) -> Any:
    if isinstance(v, list):
        return ";".join(str(x) for x in v)
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return ""
    return v


def load_status(out_dir: Path) -> dict[str, Any]:
    p = out_dir / "status.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"schema_version": SCHEMA_VERSION, "adapters": {}}


def run_adapters(adapters: list[Adapter], out_dir: Path) -> dict[str, Any]:
    """Run each adapter in isolation. Returns the updated status document."""
    out_dir.mkdir(parents=True, exist_ok=True)
    status = load_status(out_dir)
    for adapter in adapters:
        now = adapter.ctx.now
        prev = status["adapters"].get(adapter.id, {})
        target = out_dir / adapter.id
        tmp = out_dir / f".tmp-{adapter.id}"
        if tmp.exists():
            shutil.rmtree(tmp)
        entry: dict[str, Any] = {
            "adapter_id": adapter.id,
            "description": adapter.description,
            "max_age_hours": adapter.max_age.total_seconds() / 3600,
            "last_attempt_at": now.isoformat(),
            "last_success_at": prev.get("last_success_at"),
            "retrieved_at": prev.get("retrieved_at"),
        }
        try:
            raw = adapter.fetch()
            raw = adapter.validate(raw)
            ds = adapter.normalize(raw)
            adapter.emit(ds, tmp)
            if target.exists():
                shutil.rmtree(target)
            os.replace(tmp, target)
            entry.update(
                ok=True,
                error=None,
                last_success_at=now.isoformat(),
                retrieved_at=ds.retrieved_at.isoformat(),
            )
            log.info("%s: ok", adapter.id)
        except Exception as e:  # noqa: BLE001 - isolation boundary by design
            log.error("%s: FAILED, keeping last good data\n%s", adapter.id, traceback.format_exc())
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
            entry.update(ok=False, error=f"{type(e).__name__}: {str(e)[:500]}")
        entry["has_data"] = target.exists()
        status["adapters"][adapter.id] = entry
    status["schema_version"] = SCHEMA_VERSION
    status["updated_at"] = datetime.now(UTC).isoformat()
    write_json(out_dir / "status.json", status)
    return status
