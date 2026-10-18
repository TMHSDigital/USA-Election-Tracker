from __future__ import annotations

import json
from pathlib import Path

from ingest.compose import Composer
from ingest.core.adapter import Context, run_adapters

from test_adapters import ADAPTERS

ATTRS = {"fec": {"min_rows": 5}, "history": {"min_rows": 10}}
NAMES = ["state_offices", "candidates_official", "legislators", "fec", "history", "boundaries"]


def build(ctx: Context, tmp_path: Path) -> tuple[Path, dict]:
    adapters = []
    for n in NAMES:
        a = ADAPTERS[n](ctx)
        for k, v in ATTRS.get(n, {}).items():
            setattr(a, k, v)
        adapters.append(a)
    run_adapters(adapters, ctx.out_dir)
    out = tmp_path / "site"
    meta = Composer(ctx.out_dir, out, ctx.repo_root, now=ctx.now).run()
    return out, meta


def race(out: Path, rid: str) -> dict:
    return json.loads((out / "races" / f"{rid}.json").read_text(encoding="utf-8"))


def test_race_list(ctx: Context, tmp_path: Path) -> None:
    out, _ = build(ctx, tmp_path)
    index = json.loads((out / "races.json").read_text())
    house = [r for r in index if r["office"] == "house"]
    assert len(house) == 436  # 435 plus the DC delegate
    senate = {(r["state_po"], r["special"]) for r in index if r["office"] == "senate"}
    assert ("GA", False) in senate
    assert any(r["office"] == "governor" and r["state_po"] == "GA" for r in index)


def test_ballot_order_used_when_complete(ctx: Context, tmp_path: Path) -> None:
    out, _ = build(ctx, tmp_path)
    r = race(out, "2026-house-de-00")
    assert r["order_method"] == "ballot"
    assert [c["name"] for c in r["candidates"]] == ["First Person", "Second Person",
                                                    "Third Person"]
    assert r["candidate_list"]["status"] == "official"


def test_alphabetical_by_last_name_otherwise(ctx: Context, tmp_path: Path) -> None:
    out, _ = build(ctx, tmp_path)
    r = race(out, "2026-governor-ga")
    assert r["order_method"] == "alphabetical"
    assert [c["name"] for c in r["candidates"]] == ["Zed Alpha", "Bob Mike", "Amy Zulu"]


def test_not_found_list_is_unavailable(ctx: Context, tmp_path: Path) -> None:
    out, _ = build(ctx, tmp_path)
    r = race(out, "2026-governor-wy")
    assert r["candidate_list"]["status"] == "unavailable"
    assert r["candidates"] == []


def test_fec_fallback_labeled(ctx: Context, tmp_path: Path) -> None:
    out, _ = build(ctx, tmp_path)
    r = race(out, "2026-senate-ga")
    assert r["candidate_list"]["status"] == "fec_registrants"
    assert r["candidates"]
    assert all(c["list_status"] == "fec_registrants" for c in r["candidates"])


def test_every_source_id_resolves(ctx: Context, tmp_path: Path) -> None:
    """Citation coverage: every source id referenced anywhere is defined in sources.json."""
    out, _ = build(ctx, tmp_path)
    defined = {s["source_id"] for s in json.loads((out / "sources.json").read_text())}
    used: set[str] = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "source_ids":
                    assert v, "empty source_ids"
                    used.update(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    for p in (out / "races").glob("*.json"):
        walk(json.loads(p.read_text(encoding="utf-8")))
    walk(json.loads((out / "states.json").read_text()))
    assert used and used <= defined, used - defined


def test_figures_have_sources(ctx: Context, tmp_path: Path) -> None:
    out, _ = build(ctx, tmp_path)
    for p in (out / "races").glob("*.json"):
        r = json.loads(p.read_text(encoding="utf-8"))
        for c in r["candidates"]:
            assert c["source_ids"]
            if c["finance"]:
                assert c["finance"]["source_ids"]
        for h in r["history"]:
            assert h["source_ids"]


def test_compose_with_no_data_at_all(tmp_path: Path, repo: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    meta = Composer(empty, tmp_path / "site", repo).run()
    assert (tmp_path / "site" / "races.json").exists()
    assert any("legislators" in w for w in meta["warnings"])


def test_downloads_manifest(ctx: Context, tmp_path: Path) -> None:
    out, _ = build(ctx, tmp_path)
    manifest = json.loads((out / "downloads" / "index.json").read_text())
    names = {m["name"] for m in manifest}
    assert {"candidates", "fec-finance", "history", "sources"} <= names
    for m in manifest:
        for f in m["files"]:
            assert (out / "downloads" / f).exists()
