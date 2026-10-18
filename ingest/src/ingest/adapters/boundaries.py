"""Congressional district boundaries for the 2026 election, versioned by election year.

Geometry comes from Census TIGER/Line per-state files (cd120 for 2026, with
per-state overrides in data/seeds/boundary-sets-2026.yaml). Two outputs per
state:
  display/<st>.geojson  heavily simplified, for maps and static SVG outlines
  lookup/<st>.geojson   lightly simplified, for client-side point-in-polygon
plus states.geojson (state outlines) used to pick which lookup file to load.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import shapefile  # pyshp
import yaml
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from ..core.adapter import Adapter, Dataset, ValidationFailed
from ..core.http import Response
from ..core.models import BoundarySet, SourceRecord
from ..core.registry import load_registry, source_record
from ..core.states import STATES, State

TIGER = "https://www2.census.gov/geo/tiger"
DISPLAY_TOLERANCE = 0.003  # degrees, roughly 300 m
LOOKUP_TOLERANCE = 0.0002  # degrees, roughly 20 m
STATE_TOLERANCE = 0.01


@dataclass
class StateFile:
    state: State
    year: int
    layer: str
    resp: Response
    plan: dict[str, Any]


def tiger_url(year: int, layer: str, fips: str) -> str:
    return f"{TIGER}/TIGER{year}/CD/tl_{year}_{fips}_{layer}.zip"


def _round(obj: Any, nd: int) -> Any:
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, (list, tuple)):
        return [_round(x, nd) for x in obj]
    return obj


def _feature(geom: BaseGeometry, props: dict[str, Any], nd: int) -> dict[str, Any]:
    g = mapping(geom)
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": g["type"], "coordinates": _round(g["coordinates"], nd)},
    }


def _fc(features: list[dict[str, Any]], meta: dict[str, Any]) -> bytes:
    return json.dumps(
        {"type": "FeatureCollection", "metadata": meta, "features": features}, separators=(",", ":")
    ).encode("utf-8")


def read_districts(sf: StateFile) -> dict[int, BaseGeometry]:
    with zipfile.ZipFile(io.BytesIO(sf.resp.content)) as zf:
        names = zf.namelist()

        def member(ext: str) -> io.BytesIO:
            match = [n for n in names if n.lower().endswith(ext)]
            if len(match) != 1:
                raise ValidationFailed(f"{sf.resp.url}: expected one {ext}, got {match}")
            return io.BytesIO(zf.read(match[0]))

        reader = shapefile.Reader(shp=member(".shp"), shx=member(".shx"), dbf=member(".dbf"))
        fields = [f[0] for f in reader.fields[1:]]
        fp_field = next(
            (f for f in fields if f.upper().startswith("CD") and f.upper().endswith("FP")), None
        )
        if fp_field is None:
            raise ValidationFailed(f"{sf.resp.url}: no CDxxxFP field in {fields}")
        out: dict[int, BaseGeometry] = {}
        for rec in reader.iterShapeRecords():
            code = str(rec.record[fp_field]).strip()
            if code.upper() == "ZZ":
                continue  # unassigned water areas
            n = int(code)
            if n in (0, 98):  # at-large and DC delegate
                n = 0
            geom = shape(rec.shape.__geo_interface__)
            if not geom.is_valid:
                geom = geom.buffer(0)
            out[n] = unary_union([out[n], geom]) if n in out else geom
    return out


class BoundariesAdapter(Adapter):
    id = "boundaries"
    description = "Congressional district boundaries for the 2026 election (Census TIGER/Line)"
    max_age = timedelta(days=8)

    def plan(self) -> dict[str, Any]:
        path = self.ctx.repo_root / "data" / "seeds" / "boundary-sets-2026.yaml"
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def fetch(self) -> list[StateFile]:
        plan = self.plan()
        default = plan["default"]
        files = []
        for st in STATES:
            override = plan.get("overrides", {}).get(st.po, {})
            year = override.get("tiger_year", default["tiger_year"])
            layer = override.get("layer", default["layer"])
            info = {**default, **plan.get("changed_for_2026", {}).get(st.po, {}), **override}
            resp = self.ctx.http.get(tiger_url(year, layer, st.fips))
            files.append(StateFile(st, year, layer, resp, info))
        return files

    def normalize(self, files: list[StateFile]) -> Dataset:
        registry = load_registry(self.ctx.repo_root)
        sources: dict[str, SourceRecord] = {}
        sets: list[BoundarySet] = []
        extra: dict[str, bytes] = {}
        outlines = []
        errors = []
        for sf in files:
            st = sf.state
            sid = f"census_tiger_{sf.layer}_{sf.year}"
            if sid not in sources:
                sources[sid] = source_record(
                    registry,
                    "census_tiger_cd",
                    self.ctx.now,
                    sf.resp.last_modified,
                    url=f"{TIGER}/TIGER{sf.year}/CD/",
                ).model_copy(
                    update={
                        "source_id": sid,
                        "name": f"Census TIGER/Line {sf.year} congressional districts ({sf.layer})",
                    }
                )
            districts = read_districts(sf)
            expected = {0} if st.house_seats == 1 else set(range(1, st.house_seats + 1))
            if set(districts) != expected:
                errors.append(f"{st.po}: districts {sorted(districts)} != {sorted(expected)}")
                continue
            set_id = f"cd-2026-{st.po.lower()}"
            meta = {
                "boundary_set_id": set_id,
                "election_year": 2026,
                "state_po": st.po,
                "source_id": sid,
                "tiger_year": sf.year,
                "layer": sf.layer,
            }
            disp, look = [], []
            for n in sorted(districts):
                g = districts[n]
                props = {"state_po": st.po, "district": n}
                disp.append(
                    _feature(g.simplify(DISPLAY_TOLERANCE, preserve_topology=True), props, 3)
                )
                look.append(
                    _feature(g.simplify(LOOKUP_TOLERANCE, preserve_topology=True), props, 5)
                )
            extra[f"display/{st.po.lower()}.geojson"] = _fc(disp, meta)
            extra[f"lookup/{st.po.lower()}.geojson"] = _fc(look, meta)
            outline = unary_union(list(districts.values()))
            outlines.append(
                _feature(
                    outline.simplify(STATE_TOLERANCE, preserve_topology=True),
                    {"state_po": st.po},
                    3,
                )
            )
            sets.append(
                BoundarySet(
                    boundary_set_id=set_id,
                    election_year=2026,
                    state_po=st.po,
                    district_count=st.house_seats,
                    origin="census_tiger",
                    enacting_instrument=sf.plan["enacting_instrument"],
                    enacting_instrument_url=sf.plan.get("enacting_instrument_url"),
                    display_path=f"display/{st.po.lower()}.geojson",
                    lookup_path=f"lookup/{st.po.lower()}.geojson",
                    source_ids=[sid],
                )
            )
        if errors:
            raise ValidationFailed("boundary validation failed: " + "; ".join(errors))
        extra["states.geojson"] = _fc(outlines, {"election_year": 2026})
        return Dataset(
            tables={"boundary_sets": sets},
            sources=list(sources.values()),
            retrieved_at=self.ctx.now,
            extra_files=extra,
        )
