"""Historical general election results (certified, as compiled by academic datasets).

- U.S. Senate: MIT Election Data + Science Lab, "U.S. Senate statewide 1976-2024" (CC0).
- U.S. House and Governor: Cha, Kuriwaki and Snyder, "Candidates in American General
  Elections" (CC0), which downloads without a guestbook. MEDSL's House file needs a
  guestbook response, so it is not fetched automatically.

House history is keyed by district number. District lines change between
cycles, so the site labels these as results under the boundaries in effect
at the time.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from ..core.adapter import Adapter, Dataset, ValidationFailed
from ..core.http import Response
from ..core.models import HistoricalResult, Office
from ..core.registry import load_registry, source_record
from ..core.states import BY_PO

MEDSL_SENATE_URL = "https://dataverse.harvard.edu/api/access/datafile/13887039?format=original"
SNYDER_URL = "https://dataverse.harvard.edu/api/access/datafile/13461690"
MIN_YEAR = 2006
SNYDER_OFFICES = {"H": Office.HOUSE, "G": Office.GOVERNOR}


@dataclass
class HistoryRaw:
    senate: Response
    snyder: Response


def _num(v: str) -> int | None:
    v = v.strip().strip('"')
    if v in ("", "NA"):
        return None
    return int(float(v))


class HistoryAdapter(Adapter):
    id = "history"
    description = "Historical general election results (MEDSL, Cha-Kuriwaki-Snyder)"
    max_age = timedelta(days=30)
    min_rows = 5000

    def fetch(self) -> HistoryRaw:
        return HistoryRaw(senate=self.ctx.http.get(MEDSL_SENATE_URL),
                          snyder=self.ctx.http.get(SNYDER_URL))

    def validate(self, raw: HistoryRaw) -> HistoryRaw:
        head = raw.senate.text.splitlines()[0]
        for col in ("year", "state_po", "stage", "special", "candidate", "party_detailed",
                    "writein", "mode", "candidatevotes", "totalvotes"):
            if col not in head.split(","):
                raise ValidationFailed(f"MEDSL senate column missing: {col}")
        head2 = raw.snyder.text.splitlines()[0].split("\t")
        for col in ("year", "state", "office", "dist", "type", "party_formal", "name_snyder",
                    "candidatevotes", "totalvotes"):
            if col not in head2:
                raise ValidationFailed(f"Snyder column missing: {col}")
        return raw

    def normalize(self, raw: HistoryRaw) -> Dataset:
        registry = load_registry(self.ctx.repo_root)
        s_sen = source_record(registry, "medsl_senate", self.ctx.now, raw.senate.last_modified)
        s_sny = source_record(registry, "snyder_candidates", self.ctx.now,
                              raw.snyder.last_modified)
        rows: list[HistoricalResult] = []

        # Senate: sum vote modes per candidate; keep general elections only.
        agg: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
        for r in csv.DictReader(io.StringIO(raw.senate.text)):
            if r["stage"] != "gen" or int(r["year"]) < MIN_YEAR or r["state_po"] not in BY_PO:
                continue
            key = (int(r["year"]), r["state_po"], r["special"] == "True", r["candidate"] or "",
                   r["party_detailed"] or "", r["writein"] == "True")
            agg[key][0] += _num(r["candidatevotes"]) or 0
            agg[key][1] = max(agg[key][1], _num(r["totalvotes"]) or 0)
        for (year, po, special, cand, party, writein), (votes, total) in agg.items():
            rows.append(HistoricalResult(
                year=year, office=Office.SENATE, state_po=po, special=special, stage="general",
                candidate_name=cand or "(not named in source)", party_label=party,
                votes=votes, total_votes=total or None, writein=writein,
                source_ids=[s_sen.source_id]))

        for r in csv.DictReader(io.StringIO(raw.snyder.text), delimiter="\t"):
            office = SNYDER_OFFICES.get(r["office"].strip('"'))
            po = r["state"].strip('"')
            year = _num(r["year"])
            if office is None or po not in BY_PO or year is None or year < MIN_YEAR:
                continue
            if r["type"].strip('"') != "G":
                continue
            district = None
            if office == Office.HOUSE:
                d = _num(r["dist"])
                if d is None:
                    continue
                district = 0 if BY_PO[po].house_seats == 1 else d
            rows.append(HistoricalResult(
                year=year, office=office, state_po=po, district=district, stage="general",
                candidate_name=r["name_snyder"].strip('"'),
                party_label=r["party_formal"].strip('"'),
                votes=_num(r["candidatevotes"]), total_votes=_num(r["totalvotes"]),
                source_ids=[s_sny.source_id]))

        if len(rows) < self.min_rows:
            raise ValidationFailed(f"only {len(rows)} historical rows")
        rows.sort(key=lambda x: (x.office, x.state_po, x.district or 0, x.year,
                                 -(x.votes or 0)))
        return Dataset(tables={"history": rows}, sources=[s_sen, s_sny],
                       retrieved_at=self.ctx.now)
