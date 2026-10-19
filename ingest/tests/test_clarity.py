"""Live results adapter tests against archived Clarity data (WV 2024 general)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import FIXTURES, NOW

from ingest.adapters.clarity import CLARITY, ClarityAdapter, parse_updated
from ingest.compose import Composer
from ingest.core.adapter import Context, run_adapters
from ingest.core.http import FixtureHttp

BASE = f"{CLARITY}/WV/122766"
CONFIG = """version: 1
jurisdictions:
  - state_po: WV
    platform: clarity
    election_id: 122766
    contests:
      "U.S. SENATOR": 2026-senate-wv
      "U.S. HOUSE OF REPRESENTATIVES, 1st Congressional District": 2026-house-wv-01
  - state_po: CO
    platform: clarity
    election_id: null
    contests: {}
"""


@pytest.fixture
def live_ctx(repo: Path, tmp_path: Path) -> Context:
    (repo / "data" / "seeds" / "live-sources-2026.yaml").write_text(CONFIG, encoding="utf-8")
    routes = {
        f"{BASE}/current_ver.txt": "clarity/current_ver.txt",
        f"{BASE}/356048/json/en/summary.json": "clarity/summary.json",
        f"{BASE}/356048/json/en/electionsettings.json": "clarity/electionsettings.json",
    }
    return Context(
        http=FixtureHttp(FIXTURES, routes),
        repo_root=repo,
        out_dir=tmp_path / "raw",
        now=NOW,
        env={},
    )


def test_parse_updated() -> None:
    dt = parse_updated("12/18/2024 8:58:00 AM EST")
    assert dt is not None and dt.isoformat() == "2024-12-18T08:58:00-05:00"
    assert parse_updated("garbage") is None


def test_archived_results(live_ctx: Context) -> None:
    status = run_adapters([ClarityAdapter(live_ctx)], live_ctx.out_dir)
    entry = status["adapters"]["live_clarity"]
    assert entry["ok"], entry["error"]
    rows = json.loads((live_ctx.out_dir / "live_clarity" / "live_results.json").read_text())
    senate = [r for r in rows if r["race_id"] == "2026-senate-wv"]
    assert senate and all(r["reporting_text"] == "Counties Reporting: 53 of 55" for r in senate)
    # Only mapped contests; the presidential contest is ignored.
    assert {r["race_id"] for r in rows} == {"2026-senate-wv", "2026-house-wv-01"}
    contests = json.loads((live_ctx.out_dir / "live_clarity" / "contests.json").read_text())
    # Candidate order is the source's order, not sorted by votes.
    src = json.loads((FIXTURES / "clarity" / "summary.json").read_text())
    sen_src = next(c for c in src if c["C"] == "U.S. SENATOR")
    sen_out = next(c for c in contests if c["race_id"] == "2026-senate-wv")
    assert [c["candidate_name"] for c in sen_out["candidates"]] == sen_src["CH"]
    assert [c["votes"] for c in sen_out["candidates"]] == sen_src["V"]
    # No winner information is carried anywhere.
    blob = json.dumps(contests).lower()
    assert "winner" not in blob and '"w"' not in blob


def test_unmapped_contest_name_fails(live_ctx: Context, repo: Path) -> None:
    p = repo / "data" / "seeds" / "live-sources-2026.yaml"
    p.write_text(CONFIG.replace('"U.S. SENATOR"', '"US SENATE"'), encoding="utf-8")
    status = run_adapters([ClarityAdapter(live_ctx)], live_ctx.out_dir)
    assert not status["adapters"]["live_clarity"]["ok"]
    assert "missing" in status["adapters"]["live_clarity"]["error"]


def test_source_outage_keeps_last_good(live_ctx: Context, repo: Path, tmp_path: Path) -> None:
    assert run_adapters([ClarityAdapter(live_ctx)], live_ctx.out_dir)["adapters"]["live_clarity"][
        "ok"
    ]
    down = Context(
        http=FixtureHttp(tmp_path, {}), repo_root=repo, out_dir=live_ctx.out_dir, now=NOW, env={}
    )
    entry = run_adapters([ClarityAdapter(down)], live_ctx.out_dir)["adapters"]["live_clarity"]
    assert not entry["ok"] and entry["has_data"]


def test_compose_copies_live_only_when_enabled(
    live_ctx: Context, repo: Path, tmp_path: Path
) -> None:
    run_adapters([ClarityAdapter(live_ctx)], live_ctx.out_dir)
    off = tmp_path / "off"
    Composer(live_ctx.out_dir, off, repo, now=NOW, live_enabled=False).run()
    assert not (off / "live").exists()
    on = tmp_path / "on"
    meta = Composer(live_ctx.out_dir, on, repo, now=NOW, live_enabled=True).run()
    assert meta["live_enabled"] is True
    assert (on / "live" / "contests.json").exists()
    ids = {s["source_id"] for s in json.loads((on / "sources.json").read_text())}
    assert "clarity:wv:122766" in ids


def test_nothing_configured_is_ok(repo: Path, tmp_path: Path) -> None:
    ctx = Context(
        http=FixtureHttp(tmp_path, {}), repo_root=repo, out_dir=tmp_path / "raw", now=NOW, env={}
    )
    (repo / "data" / "seeds" / "live-sources-2026.yaml").write_text(
        "version: 1\njurisdictions: []\n", encoding="utf-8"
    )
    entry = run_adapters([ClarityAdapter(ctx)], ctx.out_dir)["adapters"]["live_clarity"]
    assert entry["ok"], entry["error"]
