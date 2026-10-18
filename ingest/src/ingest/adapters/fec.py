"""FEC bulk data: 2025-2026 candidate master (cn26) and all-candidates summary (weball26).

Bulk files avoid the OpenFEC API rate limit entirely and need no key. Column
order is checked against the FEC header files on every run so a silent layout
change fails validation instead of shifting numbers into the wrong fields.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import timedelta

from ..core.adapter import Adapter, Dataset, ValidationFailed
from ..core.http import Response
from ..core.models import FinanceSummary, Office
from ..core.registry import load_registry, source_record
from ..core.states import BY_PO
from ..core.util import parse_date

BULK = "https://www.fec.gov/files/bulk-downloads"
CYCLE = 2026
CN_URL = f"{BULK}/{CYCLE}/cn{str(CYCLE)[2:]}.zip"
WEBALL_URL = f"{BULK}/{CYCLE}/weball{str(CYCLE)[2:]}.zip"
CN_HEADER_URL = f"{BULK}/data_dictionaries/cn_header_file.csv"
# FEC publishes no weball header file; WEBALL_COLUMNS follows
# https://www.fec.gov/campaign-finance-data/all-candidates-file-description/

CN_COLUMNS = [
    "CAND_ID",
    "CAND_NAME",
    "CAND_PTY_AFFILIATION",
    "CAND_ELECTION_YR",
    "CAND_OFFICE_ST",
    "CAND_OFFICE",
    "CAND_OFFICE_DISTRICT",
    "CAND_ICI",
    "CAND_STATUS",
    "CAND_PCC",
    "CAND_ST1",
    "CAND_ST2",
    "CAND_CITY",
    "CAND_ST",
    "CAND_ZIP",
]
WEBALL_COLUMNS = [
    "CAND_ID",
    "CAND_NAME",
    "CAND_ICI",
    "PTY_CD",
    "CAND_PTY_AFFILIATION",
    "TTL_RECEIPTS",
    "TRANS_FROM_AUTH",
    "TTL_DISB",
    "TRANS_TO_AUTH",
    "COH_BOP",
    "COH_COP",
    "CAND_CONTRIB",
    "CAND_LOANS",
    "OTHER_LOANS",
    "CAND_LOAN_REPAY",
    "OTHER_LOAN_REPAY",
    "DEBTS_OWED_BY",
    "TTL_INDIV_CONTRIB",
    "CAND_OFFICE_ST",
    "CAND_OFFICE_DISTRICT",
    "SPEC_ELECTION",
    "PRIM_ELECTION",
    "RUN_ELECTION",
    "GEN_ELECTION",
    "GEN_ELECTION_PRECENT",
    "OTHER_POL_CMTE_CONTRIB",
    "POL_PTY_CONTRIB",
    "CVG_END_DT",
    "INDIV_REFUNDS",
    "CMTE_REFUNDS",
]
OFFICE_CODES = {"H": Office.HOUSE, "S": Office.SENATE}


@dataclass
class FecRaw:
    cn: Response
    weball: Response
    cn_header: Response


def _rows(resp: Response, columns: list[str]) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
        if len(names) != 1:
            raise ValidationFailed(f"expected one .txt in {resp.url}, got {names}")
        text = zf.read(names[0]).decode("latin-1")
    out = []
    for line_no, parts in enumerate(
        csv.reader(io.StringIO(text), delimiter="|", quoting=csv.QUOTE_NONE), 1
    ):
        if not parts or parts == [""]:
            continue
        if len(parts) != len(columns):
            raise ValidationFailed(
                f"{resp.url} line {line_no}: {len(parts)} fields, expected {len(columns)}"
            )
        out.append(dict(zip(columns, (p.strip() for p in parts), strict=True)))
    return out


def _money(v: str) -> float | None:
    if v == "":
        return None
    return round(float(v), 2)


class FecAdapter(Adapter):
    id = "fec"
    description = "FEC candidate master and all-candidates financial summary, 2025-2026 cycle"
    max_age = timedelta(days=3)
    min_rows = 500  # sanity floor; the real file has thousands

    def fetch(self) -> FecRaw:
        h = self.ctx.http
        return FecRaw(
            cn=h.get(CN_URL),
            weball=h.get(WEBALL_URL),
            cn_header=h.get(CN_HEADER_URL),
        )

    def validate(self, raw: FecRaw) -> FecRaw:
        got = [c.strip() for c in raw.cn_header.text.strip().splitlines()[0].split(",")]
        if got != CN_COLUMNS:
            raise ValidationFailed(f"FEC header changed at {raw.cn_header.url}: {got}")
        # weball has no header file; _rows() enforces the field count on every line.
        if len(raw.cn.content) < 1000 or len(raw.weball.content) < 1000:
            raise ValidationFailed("FEC bulk file suspiciously small")
        return raw

    def normalize(self, raw: FecRaw) -> Dataset:
        registry = load_registry(self.ctx.repo_root)
        src_cn = source_record(registry, "fec_bulk_cn", self.ctx.now, raw.cn.last_modified)
        src_wb = source_record(registry, "fec_bulk_weball", self.ctx.now, raw.weball.last_modified)

        master = {r["CAND_ID"]: r for r in _rows(raw.cn, CN_COLUMNS)}
        rows: list[FinanceSummary] = []
        seen: set[str] = set()
        for r in _rows(raw.weball, WEBALL_COLUMNS):
            cid = r["CAND_ID"]
            m = master.get(cid)
            if m is None or m["CAND_ELECTION_YR"] != str(CYCLE):
                continue
            office = OFFICE_CODES.get(m["CAND_OFFICE"])
            po = m["CAND_OFFICE_ST"]
            if office is None or po not in BY_PO:
                continue
            seen.add(cid)
            rows.append(self._row(m, office, po, r, [src_cn.source_id, src_wb.source_id]))
        # Candidates registered for 2026 with no financial summary still matter for
        # the FEC-registrant fallback list; emit them with empty money fields.
        for cid, m in master.items():
            if cid in seen or m["CAND_ELECTION_YR"] != str(CYCLE):
                continue
            office = OFFICE_CODES.get(m["CAND_OFFICE"])
            po = m["CAND_OFFICE_ST"]
            if office is None or po not in BY_PO:
                continue
            rows.append(self._row(m, office, po, None, [src_cn.source_id]))

        if len(rows) < self.min_rows:
            raise ValidationFailed(f"only {len(rows)} 2026 House/Senate candidates; expected more")
        rows.sort(key=lambda x: (x.state_po, x.office, x.district or 0, x.candidate_name))
        return Dataset(
            tables={"finance": rows}, sources=[src_cn, src_wb], retrieved_at=self.ctx.now
        )

    @staticmethod
    def _row(
        m: dict[str, str], office: Office, po: str, w: dict[str, str] | None, source_ids: list[str]
    ) -> FinanceSummary:
        district = None
        if office == Office.HOUSE:
            d = m["CAND_OFFICE_DISTRICT"]
            district = int(d) if d.isdigit() else None
            if BY_PO[po].house_seats == 1:
                district = 0
        ici = m["CAND_ICI"] or None
        return FinanceSummary(
            fec_candidate_id=m["CAND_ID"],
            candidate_name=m["CAND_NAME"],
            state_po=po,
            office=office,
            district=district,
            party_code=m["CAND_PTY_AFFILIATION"] or None,
            incumbent_challenge=ici if ici in {"I", "C", "O"} else None,
            election_year=int(m["CAND_ELECTION_YR"]),
            candidate_status=m["CAND_STATUS"] or None,
            receipts=_money(w["TTL_RECEIPTS"]) if w else None,
            disbursements=_money(w["TTL_DISB"]) if w else None,
            cash_on_hand=_money(w["COH_COP"]) if w else None,
            coverage_end_date=parse_date(w["CVG_END_DT"]) if w and w["CVG_END_DT"] else None,
            source_ids=source_ids,
        )
