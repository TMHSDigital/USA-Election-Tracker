from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingest.adapters import ADAPTERS
from ingest.adapters.fec import FecAdapter
from ingest.adapters.history import HistoryAdapter
from ingest.core.adapter import Context, run_adapters
from ingest.core.http import FixtureHttp
from ingest.core.states import STATES


def run(ctx: Context, *names: str, **attrs) -> dict:
    adapters = []
    for n in names:
        a = ADAPTERS[n](ctx)
        for k, v in attrs.get(n, {}).items():
            setattr(a, k, v)
        adapters.append(a)
    return run_adapters(adapters, ctx.out_dir)


def load(ctx: Context, adapter: str, table: str) -> list[dict]:
    return json.loads((ctx.out_dir / adapter / f"{table}.json").read_text(encoding="utf-8"))


def test_house_seats_total() -> None:
    assert sum(s.house_seats for s in STATES if s.po != "DC") == 435
    assert len(STATES) == 51


def test_fec_parses_fixture(ctx: Context) -> None:
    status = run(ctx, "fec", fec={"min_rows": 5})
    assert status["adapters"]["fec"]["ok"], status["adapters"]["fec"]["error"]
    rows = load(ctx, "fec", "finance")
    assert all(r["election_year"] == 2026 for r in rows)
    assert {r["state_po"] for r in rows} <= {"AK", "DE", "WY", "GA"}
    with_money = [r for r in rows if r["receipts"] is not None]
    assert with_money and all(r["coverage_end_date"] for r in with_money)
    assert all(r["source_ids"] for r in rows)


def test_fec_header_change_fails_and_keeps_last_good(ctx: Context, fixture_dir: Path) -> None:
    assert run(ctx, "fec", fec={"min_rows": 5})["adapters"]["fec"]["ok"]
    before = (ctx.out_dir / "fec" / "finance.json").read_bytes()
    (fixture_dir / "fec" / "cn_header_file.csv").write_text("CAND_ID,SOMETHING_NEW\n")
    status = run(ctx, "fec", fec={"min_rows": 5})
    entry = status["adapters"]["fec"]
    assert not entry["ok"] and "header changed" in entry["error"]
    assert entry["has_data"]
    assert (ctx.out_dir / "fec" / "finance.json").read_bytes() == before


def test_fec_min_rows_guard(ctx: Context) -> None:
    status = run(ctx, "fec")  # default floor of 500 is above the fixture size
    assert not status["adapters"]["fec"]["ok"]
    assert not (ctx.out_dir / "fec").exists()


def test_legislators(ctx: Context) -> None:
    status = run(ctx, "legislators")
    assert status["adapters"]["legislators"]["ok"], status["adapters"]["legislators"]["error"]
    rows = load(ctx, "legislators", "incumbents")
    senators = [r for r in rows if r["office"] == "senate"]
    assert len(senators) == 100
    assert any(r["senate_class"] == 2 for r in senators)


def test_history(ctx: Context) -> None:
    status = run(ctx, "history", history={"min_rows": 10})
    assert status["adapters"]["history"]["ok"], status["adapters"]["history"]["error"]
    rows = load(ctx, "history", "history")
    offices = {r["office"] for r in rows}
    assert {"senate", "house", "governor"} <= offices
    assert all(r["year"] >= 2006 for r in rows)


def test_boundaries_synthetic(ctx: Context) -> None:
    status = run(ctx, "boundaries")
    assert status["adapters"]["boundaries"]["ok"], status["adapters"]["boundaries"]["error"]
    sets = {b["state_po"]: b for b in load(ctx, "boundaries", "boundary_sets")}
    assert len(sets) == 51
    assert sets["TX"]["district_count"] == 38
    assert "HB 4" in sets["TX"]["enacting_instrument"]
    assert sets["MO"]["source_ids"] == ["census_tiger_cd119_2025"]
    look = json.loads((ctx.out_dir / "boundaries" / "lookup" / "dc.geojson").read_text())
    assert [f["properties"]["district"] for f in look["features"]] == [0]
    assert look["metadata"]["election_year"] == 2026


def test_boundaries_wrong_district_count_fails(ctx: Context, fixture_dir: Path) -> None:
    from conftest import make_tiger_zip

    (fixture_dir / "tiger" / "2026_48.zip").write_bytes(make_tiger_zip("48", "cd120", 36))
    status = run(ctx, "boundaries")
    assert not status["adapters"]["boundaries"]["ok"]
    assert "TX" in status["adapters"]["boundaries"]["error"]


def test_seed_candidates(ctx: Context) -> None:
    status = run(ctx, "candidates_official")
    assert status["adapters"]["candidates_official"]["ok"], \
        status["adapters"]["candidates_official"]["error"]
    rows = load(ctx, "candidates_official", "seed_candidates")
    assert {r["race_id"] for r in rows} == {"2026-governor-ga", "2026-house-de-00"}
    cov = {(c["state_po"], c["office"]): c["status"]
           for c in load(ctx, "candidates_official", "seed_coverage")}
    assert cov[("WY", "governor")] == "not_found"
    assert cov[("GA", "governor")] == "official"


def test_seed_bad_district_rejected(ctx: Context, repo: Path) -> None:
    p = repo / "data" / "seeds" / "federal-candidates-2026" / "GA.csv"
    p.write_text(
        "state_po,office,district,special,candidate_name,ballot_name,party_ballot_label,"
        "incumbent,ballot_order,source_url,source_title,retrieved_at,notes\n"
        "GA,US House,15,false,X Y,X Y,Democratic,false,,https://sos.ga.gov/a,t,2026-10-18,\n",
        encoding="utf-8")
    status = run(ctx, "candidates_official")
    assert not status["adapters"]["candidates_official"]["ok"]
    assert "district 15" in status["adapters"]["candidates_official"]["error"]


def test_state_offices(ctx: Context) -> None:
    status = run(ctx, "state_offices")
    assert status["adapters"]["state_offices"]["ok"], status["adapters"]["state_offices"]["error"]
    assert len(load(ctx, "state_offices", "state_offices")) == 51


def test_acs_without_key_fails_cleanly(ctx: Context) -> None:
    status = run(ctx, "acs")
    assert not status["adapters"]["acs"]["ok"]
    assert "CENSUS_API_KEY" in status["adapters"]["acs"]["error"]


def test_all_sources_failed_keeps_last_good(ctx: Context, repo: Path, tmp_path: Path) -> None:
    attrs = {"fec": {"min_rows": 5}, "history": {"min_rows": 10}}
    names = ["state_offices", "candidates_official", "legislators", "fec", "history",
             "boundaries"]
    first = run(ctx, *names, **attrs)
    assert all(first["adapters"][n]["ok"] for n in names)
    snapshot = {n: (ctx.out_dir / n / "_meta.json").read_bytes() for n in names}

    broken = Context(http=FixtureHttp(tmp_path, {}), repo_root=repo, out_dir=ctx.out_dir,
                     now=ctx.now, env={})
    # Seeds are local files; break them too so every adapter fails.
    (repo / "data" / "seeds" / "state-election-offices.yaml").write_text("states: []\n")
    (repo / "data" / "seeds" / "governors-2026.csv").write_text("garbage\n1\n")
    for f in (repo / "data" / "seeds" / "federal-candidates-2026").glob("*.csv"):
        f.unlink()
    second = run(broken, *names, **attrs)
    for n in names:
        e = second["adapters"][n]
        assert not e["ok"], n
        assert e["has_data"], n
        assert e["last_success_at"] == first["adapters"][n]["last_success_at"]
        assert (ctx.out_dir / n / "_meta.json").read_bytes() == snapshot[n]


@pytest.mark.parametrize("name", list(ADAPTERS))
def test_every_adapter_has_metadata(name: str) -> None:
    a = ADAPTERS[name]
    assert a.id == name and a.description
