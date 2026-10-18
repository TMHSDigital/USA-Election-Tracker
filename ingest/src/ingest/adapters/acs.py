"""Census ACS 5-year estimates by congressional district.

The latest ACS 5-year release (2020-2024) is tabulated for 119th Congress
districts. For states whose map changed for 2026, those tabulations describe
different geography, so we emit nothing for them and the site shows
"Not available for this district's 2026 boundaries". No approximation in v0.

Requires CENSUS_API_KEY (free; the API rejects keyless requests).
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import yaml

from ..core.adapter import Adapter, Dataset, ValidationFailed
from ..core.models import DistrictDemographics
from ..core.registry import load_registry, source_record
from ..core.states import BY_FIPS

VINTAGE = "2024"
URL = f"https://api.census.gov/data/{VINTAGE}/acs/acs5"
VARIABLES = {
    "B01003_001": "Total population",
    "B01002_001": "Median age (years)",
    "B19013_001": "Median household income (dollars)",
}
# Census uses large negative sentinels for unavailable estimates.
SENTINELS = {-666666666, -999999999, -888888888, -222222222, -333333333, -555555555}


class AcsAdapter(Adapter):
    id = "acs"
    description = f"Census ACS 5-year ({VINTAGE}) estimates by congressional district"
    max_age = timedelta(days=30)

    def fetch(self) -> list[list[Any]]:
        key = self.ctx.env.get("CENSUS_API_KEY")
        if not key:
            raise ValidationFailed("CENSUS_API_KEY not set")
        fields = ["NAME"] + [f"{v}{s}" for v in VARIABLES for s in ("E", "M")]
        resp = self.ctx.http.get(URL, params={"get": ",".join(fields),
                                              "for": "congressional district:*",
                                              "in": "state:*", "key": key})
        return json.loads(resp.content)

    def validate(self, raw: list[list[Any]]) -> list[list[Any]]:
        if not raw or "congressional district" not in raw[0]:
            raise ValidationFailed("unexpected ACS response header")
        if len(raw) < 430:
            raise ValidationFailed(f"only {len(raw) - 1} ACS district rows")
        return raw

    def normalize(self, raw: list[list[Any]]) -> Dataset:
        registry = load_registry(self.ctx.repo_root)
        src = source_record(registry, "census_acs5", self.ctx.now)
        plan = yaml.safe_load((self.ctx.repo_root / "data" / "seeds" /
                               "boundary-sets-2026.yaml").read_text(encoding="utf-8"))
        changed = set(plan.get("changed_for_2026", {}))
        header = raw[0]
        idx = {h: i for i, h in enumerate(header)}
        rows: list[DistrictDemographics] = []
        for rec in raw[1:]:
            st = BY_FIPS.get(rec[idx["state"]])
            if st is None or st.po in changed:
                continue
            cd = rec[idx["congressional district"]]
            if cd == "ZZ":
                continue
            n = int(cd)
            district = 0 if st.house_seats == 1 else n
            for var, label in VARIABLES.items():
                rows.append(DistrictDemographics(
                    state_po=st.po, district=district, boundary_vintage="cd119",
                    variable=var, label=label,
                    estimate=_val(rec[idx[var + "E"]]),
                    margin_of_error=_val(rec[idx[var + "M"]]),
                    source_ids=[src.source_id]))
        rows.sort(key=lambda r: (r.state_po, r.district, r.variable))
        return Dataset(tables={"demographics": rows}, sources=[src], retrieved_at=self.ctx.now)


def _val(v: Any) -> float | None:
    if v in (None, ""):
        return None
    f = float(v)
    return None if int(f) in SENTINELS else f
