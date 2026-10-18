"""Current members of Congress from unitedstates/congress-legislators (CC0).

Used for: incumbent flags, FEC candidate ids of incumbents (for finance
matching), and the list of Senate seats up in 2026 (class 2).
"""

from __future__ import annotations

import json
from typing import Any

from ..core.adapter import Adapter, Dataset, ValidationFailed
from ..core.http import Response
from ..core.models import Incumbent, Office
from ..core.registry import load_registry, source_record
from ..core.states import BY_PO

URL = "https://unitedstates.github.io/congress-legislators/legislators-current.json"


class LegislatorsAdapter(Adapter):
    id = "legislators"
    description = "Current members of Congress (unitedstates/congress-legislators)"

    def fetch(self) -> Response:
        return self.ctx.http.get(URL)

    def validate(self, raw: Response) -> list[dict[str, Any]]:
        data = json.loads(raw.content)
        if not isinstance(data, list) or not 500 <= len(data) <= 560:
            raise ValidationFailed(f"unexpected legislators payload size {len(data)}")
        self._resp = raw
        return data

    def normalize(self, data: list[dict[str, Any]]) -> Dataset:
        registry = load_registry(self.ctx.repo_root)
        src = source_record(registry, "congress_legislators", self.ctx.now,
                            self._resp.last_modified)
        rows: list[Incumbent] = []
        for p in data:
            term = p["terms"][-1]
            po = term["state"]
            if po not in BY_PO:
                continue  # territories other than DC are out of scope for v0
            name = p["name"].get("official_full") or f"{p['name']['first']} {p['name']['last']}"
            if term["type"] == "sen":
                office, district, cls = Office.SENATE, None, term.get("class")
            else:
                office, cls = Office.HOUSE, None
                district = int(term.get("district", 0))
                if BY_PO[po].house_seats == 1:
                    district = 0
            rows.append(
                Incumbent(
                    bioguide_id=p["id"]["bioguide"],
                    name=name,
                    office=office,
                    state_po=po,
                    district=district,
                    senate_class=cls,
                    term_end=term.get("end"),
                    party=term.get("party", ""),
                    fec_candidate_ids=list(p["id"].get("fec", [])),
                    source_ids=[src.source_id],
                )
            )
        senators = [r for r in rows if r.office == Office.SENATE]
        if len(senators) != 100:
            raise ValidationFailed(f"expected 100 senators, got {len(senators)}")
        rows.sort(key=lambda r: (r.state_po, r.office, r.district or 0, r.name))
        return Dataset(tables={"incumbents": rows}, sources=[src], retrieved_at=self.ctx.now)
