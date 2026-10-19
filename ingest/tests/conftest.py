from __future__ import annotations

import io
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
import shapefile

from ingest.adapters.boundaries import tiger_url
from ingest.adapters.fec import CN_HEADER_URL, CN_URL, WEBALL_URL
from ingest.adapters.history import MEDSL_SENATE_URL, SNYDER_URL
from ingest.adapters.legislators import URL as LEGISLATORS_URL
from ingest.core.adapter import Context
from ingest.core.http import FixtureHttp
from ingest.core.states import STATES

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)

ROUTES = {
    CN_URL: "fec/cn26.zip",
    WEBALL_URL: "fec/weball26.zip",
    CN_HEADER_URL: "fec/cn_header_file.csv",
    LEGISLATORS_URL: "legislators-current.json",
    MEDSL_SENATE_URL: "history/senate.csv",
    SNYDER_URL: "history/snyder.tab",
}

GOV_SEED = """state_po,state_name,office,election_date,candidate_name,ballot_name,party_ballot_label,incumbent,running_mate,ballot_order,source_url,source_title,retrieved_at,notes
GA,Georgia,Governor,2026-11-03,Zed Alpha,Zed Alpha,Libertarian,false,,,https://sos.ga.gov/list.pdf,GA list,2026-10-18,
GA,Georgia,Governor,2026-11-03,Amy Zulu,Amy Zulu,Democratic,false,,,https://sos.ga.gov/list.pdf,GA list,2026-10-18,
GA,Georgia,Governor,2026-11-03,Bob Mike,Bob Mike,Republican,false,,,https://sos.ga.gov/list.pdf,GA list,2026-10-18,
WY,Wyoming,Governor,2026-11-03,,,,,,,https://sos.wyo.gov/x,WY,2026-10-18,OFFICIAL LIST NOT FOUND: tried sos.wyo.gov
"""

FED_SEED_DE = """state_po,office,district,special,candidate_name,ballot_name,party_ballot_label,incumbent,ballot_order,source_url,source_title,retrieved_at,notes
DE,US House,0,false,Second Person,Second Person,Republican,false,2,https://elections.delaware.gov/list.pdf,DE list,2026-10-18,at-large
DE,US House,0,false,First Person,First Person,Democratic,false,1,https://elections.delaware.gov/list.pdf,DE list,2026-10-18,at-large
DE,US House,0,false,Third Person,Third Person,Independent Party of Delaware,false,3,https://elections.delaware.gov/list.pdf,DE list,2026-10-18,at-large
"""


def make_office_seed() -> str:
    lines = ["version: 1", "retrieved_at: 2026-10-18", "states:"]
    for s in STATES:
        lines += [
            f"  - state_po: {s.po}",
            f"    state_name: {s.name}",
            f'    state_fips: "{s.fips}"',
            f"    office_name: {s.name} Election Office",
            f"    homepage_url: https://elections.example.gov/{s.po.lower()}",
            f"    voter_info_url: https://elections.example.gov/{s.po.lower()}/vote",
            f"    results_url: https://results.example.gov/{s.po.lower()}",
            "    results_platform: unknown",
            "    general_election_date: 2026-11-03",
            "    retrieved_at: 2026-10-18",
            '    notes: ""',
        ]
    return "\n".join(lines) + "\n"


def make_tiger_zip(fips: str, layer: str, n: int) -> bytes:
    """Synthetic district shapefile: n adjacent unit squares."""
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
    fp = f"{layer.upper()}FP"
    w.field("STATEFP", "C", 2)
    w.field(fp, "C", 2)
    codes = ["00"] if n == 1 else [f"{i:02d}" for i in range(1, n + 1)]
    if fips == "11":
        codes = ["98"]
    for i, code in enumerate(codes):
        x = float(i)
        w.poly([[[x, 0.0], [x, 1.0], [x + 1, 1.0], [x + 1, 0.0], [x, 0.0]]])
        w.record(fips, code)
    w.close()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        base = f"tl_x_{fips}_{layer}"
        zf.writestr(base + ".shp", shp.getvalue())
        zf.writestr(base + ".shx", shx.getvalue())
        zf.writestr(base + ".dbf", dbf.getvalue())
    return buf.getvalue()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal repo root with the real registry and small seed files."""
    root = tmp_path / "repo"
    (root / "sources").mkdir(parents=True)
    shutil.copy(REPO / "sources" / "registry.yaml", root / "sources" / "registry.yaml")
    seeds = root / "data" / "seeds"
    (seeds / "federal-candidates-2026").mkdir(parents=True)
    shutil.copy(
        REPO / "data" / "seeds" / "boundary-sets-2026.yaml", seeds / "boundary-sets-2026.yaml"
    )
    (seeds / "state-election-offices.yaml").write_text(make_office_seed(), encoding="utf-8")
    (seeds / "governors-2026.csv").write_text(GOV_SEED, encoding="utf-8")
    (seeds / "federal-candidates-2026" / "DE.csv").write_text(FED_SEED_DE, encoding="utf-8")
    return root


@pytest.fixture
def fixture_dir(tmp_path: Path) -> Path:
    d = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, d)
    tiger = d / "tiger"
    tiger.mkdir()
    for s in STATES:
        for year, layer in ((2026, "cd120"), (2025, "cd119")):
            (tiger / f"{year}_{s.fips}.zip").write_bytes(
                make_tiger_zip(s.fips, layer, s.house_seats)
            )
    return d


def all_routes() -> dict[str, str]:
    routes = dict(ROUTES)
    for s in STATES:
        for year, layer in ((2026, "cd120"), (2025, "cd119")):
            routes[tiger_url(year, layer, s.fips)] = f"tiger/{year}_{s.fips}.zip"
    return routes


@pytest.fixture
def ctx(repo: Path, fixture_dir: Path, tmp_path: Path) -> Context:
    return Context(
        http=FixtureHttp(fixture_dir, all_routes()),
        repo_root=repo,
        out_dir=tmp_path / "raw",
        now=NOW,
        env={},
    )
