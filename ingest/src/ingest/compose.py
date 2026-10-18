"""Join adapter outputs into the site-ready data bundle.

Input: the adapter output directory (one subdirectory per adapter plus
status.json), which in CI is a checkout of the `data` branch, so whatever
last good data exists is always available. Output: the bundle the Astro
build reads (races, states, sources, downloads, boundaries, status).

Compose never fetches anything. If an adapter has never produced data, the
dependent fields are simply empty and the page says so.
"""

from __future__ import annotations

import csv
import json
import logging
import shutil
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .core.adapter import write_csv, write_json
from .core.models import SCHEMA_VERSION
from .core.registry import load_registry
from .core.states import BY_PO, STATES
from .core.util import (
    first_name,
    last_name,
    race_id,
    slugify,
    sort_key_last_name,
    url_source_id,
)

log = logging.getLogger(__name__)

ELECTION_DATE = date(2026, 11, 3)
HISTORY_CYCLES = 5
# Fallback when the governors seed is missing. Cited in sources/registry.yaml as
# governors_2026_list.
GOVERNOR_STATES_2026 = [
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IA",
    "KS",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "NE",
    "NV",
    "NH",
    "NM",
    "NY",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "VT",
    "WI",
    "WY",
]
FEC_FALLBACK_STATUSES = {"C"}  # statutory candidates only


def _load(in_dir: Path, adapter: str, table: str) -> list[dict[str, Any]]:
    p = in_dir / adapter / f"{table}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def _sources(in_dir: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for meta in sorted(in_dir.glob("*/_meta.json")):
        for s in json.loads(meta.read_text(encoding="utf-8"))["sources"]:
            out[s["source_id"]] = s
    return out


def _status(in_dir: Path, now: datetime) -> dict[str, Any]:
    p = in_dir / "status.json"
    status = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"adapters": {}}
    for entry in status["adapters"].values():
        last = entry.get("last_success_at")
        max_age = timedelta(hours=entry.get("max_age_hours", 48))
        too_old = last is None or now - datetime.fromisoformat(last) > max_age
        entry["stale"] = bool(too_old or not entry.get("ok"))
    return status


def _pct(votes: int | None, total: int | None) -> float | None:
    if not votes or not total:
        return None
    return round(100.0 * votes / total, 1)


class Composer:
    def __init__(
        self,
        in_dir: Path,
        out_dir: Path,
        repo_root: Path,
        now: datetime | None = None,
        live_enabled: bool = False,
    ) -> None:
        self.in_dir = in_dir
        self.out_dir = out_dir
        self.repo_root = repo_root
        self.now = now or datetime.now(UTC)
        self.live_enabled = live_enabled
        self.warnings: list[str] = []

    # ----- race list -------------------------------------------------------
    def race_keys(
        self, incumbents: list[dict], seeds: list[dict], coverage: list[dict]
    ) -> list[tuple[str, str, int | None, bool]]:
        keys: set[tuple[str, str, int | None, bool]] = set()
        for st in STATES:
            if st.house_seats == 1:
                keys.add(("house", st.po, 0, False))
            else:
                for d in range(1, st.house_seats + 1):
                    keys.add(("house", st.po, d, False))
        for inc in incumbents:
            if inc["office"] != "senate":
                continue
            if inc.get("senate_class") == 2:
                keys.add(("senate", inc["state_po"], None, False))
            elif inc.get("term_end") == ELECTION_DATE.isoformat():
                keys.add(("senate", inc["state_po"], None, True))
        for s in seeds:
            if s["office"] == "senate":
                keys.add(("senate", s["state_po"], None, bool(s["special"])))
        gov_states = {c["state_po"] for c in coverage if c["office"] == "governor"}
        gov_states |= {s["state_po"] for s in seeds if s["office"] == "governor"}
        for po in gov_states or set(GOVERNOR_STATES_2026):
            keys.add(("governor", po, None, False))
        if not incumbents:
            self.warnings.append("legislators data missing; Senate race list from seeds only")
        return sorted(keys, key=lambda k: (k[1], k[0], k[2] or 0, k[3]))

    # ----- main ------------------------------------------------------------
    def run(self) -> dict[str, Any]:
        i = self.in_dir
        registry = load_registry(self.repo_root)
        sources = _sources(i)
        status = _status(i, self.now)
        offices = {o["state_po"]: o for o in _load(i, "state_offices", "state_offices")}
        seeds = _load(i, "candidates_official", "seed_candidates")
        coverage = _load(i, "candidates_official", "seed_coverage")
        finance = _load(i, "fec", "finance")
        incumbents = _load(i, "legislators", "incumbents")
        history = _load(i, "history", "history")
        demographics = _load(i, "acs", "demographics")
        boundary_sets = {b["state_po"]: b for b in _load(i, "boundaries", "boundary_sets")}

        cov = {(c["state_po"], c["office"]): c for c in coverage}
        seeds_by_race: dict[str, list[dict]] = defaultdict(list)
        for s in seeds:
            seeds_by_race[s["race_id"]].append(s)
        fin_by_seat: dict[tuple, list[dict]] = defaultdict(list)
        fin_by_id = {}
        for f in finance:
            fin_by_seat[(f["office"], f["state_po"], f.get("district"))].append(f)
            fin_by_id[f["fec_candidate_id"]] = f
        inc_fec_ids = {fid for inc in incumbents for fid in inc.get("fec_candidate_ids", [])}
        hist_by_seat: dict[tuple, list[dict]] = defaultdict(list)
        for h in history:
            hist_by_seat[(h["office"], h["state_po"], h.get("district"))].append(h)
        demo_by_seat: dict[tuple, list[dict]] = defaultdict(list)
        for d in demographics:
            demo_by_seat[(d["state_po"], d["district"])].append(d)
        overrides = self._fec_overrides()

        keys = self.race_keys(incumbents, seeds, coverage)
        race_notes = self._race_notes(keys, sources)
        races_out: list[dict[str, Any]] = []
        candidates_flat: list[dict[str, Any]] = []
        for office, po, district, special in keys:
            rid = race_id(2026, _office(office), po, district, special)
            seat = (office, po, district if office == "house" else None)
            c = cov.get((po, office))
            candidates: list[dict[str, Any]] = []
            list_url = c.get("list_url") if c else None
            list_sources = list(c["source_ids"]) if c else []
            if c and c["status"] == "official":
                list_status = "official"
                for s in seeds_by_race.get(rid, []):
                    cand = self._official_candidate(
                        rid, s, fin_by_seat.get(seat, []), fin_by_id, inc_fec_ids, overrides
                    )
                    candidates.append(cand)
                if not candidates:
                    self.warnings.append(f"{rid}: official list for {po} has no rows for race")
            elif office in ("house", "senate") and fin_by_seat.get(seat):
                list_status = "fec_registrants"
                for f in fin_by_seat[seat]:
                    if f.get("candidate_status") not in FEC_FALLBACK_STATUSES:
                        continue
                    if f.get("election_year") != 2026:
                        continue
                    candidates.append(self._fec_candidate(rid, f))
                list_sources += ["fec_bulk_cn"]
            else:
                list_status = "unavailable"
            if not list_sources and po in offices:
                # Nothing to list; the page links the state office instead, so cite it.
                list_sources = list(offices[po]["source_ids"])

            if candidates and all(x["ballot_order"] is not None for x in candidates):
                order_method = "ballot"
                candidates.sort(key=lambda x: x["ballot_order"])
            else:
                order_method = "alphabetical"
                candidates.sort(key=lambda x: sort_key_last_name(x["name"]))

            boundary = None
            if office == "house" and po in boundary_sets:
                b = boundary_sets[po]
                boundary = {
                    k: b[k]
                    for k in (
                        "boundary_set_id",
                        "enacting_instrument",
                        "enacting_instrument_url",
                        "display_path",
                        "source_ids",
                    )
                }
            race = {
                "race_id": rid,
                "office": office,
                "state_po": po,
                "state_name": BY_PO[po].name,
                "district": district,
                "special": special,
                "election_date": ELECTION_DATE.isoformat(),
                "candidate_list": {"status": list_status, "url": list_url}
                | ({"source_ids": sorted(set(list_sources))} if list_sources else {}),
                "notes": race_notes.get(rid),
                "order_method": order_method,
                "candidates": candidates,
                "boundary": boundary,
                "history": self._history(hist_by_seat.get(seat, []), special),
                "demographics": self._demographics(
                    office, po, district, demo_by_seat, boundary_sets
                ),
                "official_results_url": (offices.get(po) or {}).get("results_url"),
            }
            races_out.append(race)
            for cand in candidates:
                candidates_flat.append(
                    {
                        "race_id": rid,
                        "state_po": po,
                        "office": office,
                        "district": district,
                        "special": special,
                        **{k: v for k, v in cand.items() if k != "finance"},
                    }
                )

        self._check_incumbents(races_out, incumbents)
        # The site cites these registry entries directly (e.g. Vote.gov links).
        used = self._used_source_ids(races_out, offices, boundary_sets) | {"vote_gov"}
        for sid in used:
            if sid not in sources and sid in registry:
                e = registry[sid]
                sources[sid] = {
                    "source_id": sid,
                    "name": e["name"],
                    "publisher": e["publisher"],
                    "url": e["url"],
                    "license": e["license"],
                    "retrieved_at": None,
                    "source_published_at": None,
                    "notes": e.get("notes", ""),
                }
        missing = sorted(used - set(sources))
        if missing:
            raise RuntimeError(f"source ids used but not defined: {missing}")
        return self._write(
            races_out,
            candidates_flat,
            offices,
            sources,
            status,
            finance,
            history,
            demographics,
            boundary_sets,
        )

    def _race_notes(self, keys: list[tuple], sources: dict[str, dict]) -> dict[str, dict]:
        import yaml

        p = self.repo_root / "data" / "seeds" / "race-notes-2026.yaml"
        if not p.exists():
            return {}
        rules = yaml.safe_load(p.read_text(encoding="utf-8")).get("rules", [])
        out: dict[str, dict] = {}
        for rule in rules:
            sid = url_source_id("state-notice", rule["source_url"])
            sources[sid] = {
                "source_id": sid,
                "name": rule["source_title"],
                "publisher": rule["publisher"],
                "url": rule["source_url"],
                "license": "Government publication, cited and linked; see publisher terms",
                "retrieved_at": str(rule["retrieved_at"]),
                "source_published_at": None,
                "notes": "",
            }
            m = rule["match"]
            for office, po, district, special in keys:
                if m.get("state_po", po) != po or m.get("office", office) != office:
                    continue
                if "district" in m and m["district"] != district:
                    continue
                rid = race_id(2026, _office(office), po, district, special)
                out[rid] = {
                    "election_type": rule["election_type"],
                    "runoff_date": str(rule["runoff_date"]) if rule.get("runoff_date") else None,
                    "source_ids": [sid],
                }
        return out

    # ----- candidates ------------------------------------------------------
    def _fec_overrides(self) -> dict[tuple[str, str], str]:
        p = self.repo_root / "data" / "seeds" / "fec-id-overrides.csv"
        out: dict[tuple[str, str], str] = {}
        if p.exists():
            with p.open(encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    out[(r["race_id"], r["candidate_name"].lower())] = r["fec_candidate_id"]
        return out

    def _official_candidate(
        self,
        rid: str,
        s: dict,
        seat_fec: list[dict],
        fin_by_id: dict[str, dict],
        inc_fec_ids: set[str],
        overrides: dict[tuple[str, str], str],
    ) -> dict[str, Any]:
        fec_id, method = None, None
        ov = overrides.get((rid, s["name"].lower()))
        if ov is not None:
            fec_id, method = (ov, "override") if ov.lower() != "none" else (None, None)
        elif s.get("fec_candidate_id"):
            fec_id, method = s["fec_candidate_id"], "seed"
        elif s["office"] in ("house", "senate"):
            fec_id, method = self._match_fec(s, seat_fec, inc_fec_ids)
        fin = fin_by_id.get(fec_id) if fec_id else None
        return {
            "candidate_id": f"{rid}--{slugify(s['name'])}",
            "name": s["name"],
            "ballot_name": s["ballot_name"],
            "party_label": s["party_label"],
            "incumbent": s["incumbent"],
            "ballot_order": s.get("ballot_order"),
            "write_in": s.get("write_in", False),
            "running_mate": s.get("running_mate"),
            "fec_candidate_id": fec_id,
            "fec_match_method": method,
            "list_status": "official",
            "source_ids": s["source_ids"],
            "finance": _finance(fin),
        }

    def _match_fec(
        self, s: dict, seat_fec: list[dict], inc_fec_ids: set[str]
    ) -> tuple[str | None, str | None]:
        """Strict match. A wrong match shows someone else's money, so ambiguity means no match."""
        pool = [f for f in seat_fec if f.get("election_year") == 2026]
        if s["incumbent"]:
            inc = [
                f
                for f in pool
                if f["fec_candidate_id"] in inc_fec_ids
                and last_name(f["candidate_name"]) == last_name(s["name"])
            ]
            if len(inc) == 1:
                return inc[0]["fec_candidate_id"], "legislators"
        ln, fn = last_name(s["name"]), first_name(s["name"])
        hits = [f for f in pool if last_name(f["candidate_name"]) == ln]
        if len(hits) > 1:
            hits = [f for f in hits if _first_compatible(first_name(f["candidate_name"]), fn)]
        if len(hits) > 1:
            active = [f for f in hits if f.get("candidate_status") == "C"]
            if len(active) == 1:
                hits = active
        if len(hits) == 1 and _first_compatible(first_name(hits[0]["candidate_name"]), fn):
            return hits[0]["fec_candidate_id"], "name"
        if len(hits) > 1:
            self.warnings.append(f"ambiguous FEC match for {s['name']} in {s['race_id']}")
        return None, None

    def _fec_candidate(self, rid: str, f: dict) -> dict[str, Any]:
        return {
            "candidate_id": f"{rid}--{slugify(f['candidate_name'])}",
            "name": f["candidate_name"],
            "ballot_name": f["candidate_name"],
            "party_label": f.get("party_code") or "",
            "incumbent": f.get("incumbent_challenge") == "I",
            "ballot_order": None,
            "write_in": False,
            "running_mate": None,
            "fec_candidate_id": f["fec_candidate_id"],
            "fec_match_method": "fec_registrant",
            "list_status": "fec_registrants",
            "source_ids": ["fec_bulk_cn"],
            "finance": _finance(f),
        }

    def _check_incumbents(self, races: list[dict], incumbents: list[dict]) -> None:
        seat_holders = defaultdict(list)
        for inc in incumbents:
            seat_holders[(inc["office"], inc["state_po"], inc.get("district"))].append(inc)
        for r in races:
            if r["office"] == "governor" or r["candidate_list"]["status"] != "official":
                continue
            seat = (r["office"], r["state_po"], r["district"])
            holders = {last_name(h["name"]) for h in seat_holders.get(seat, [])}
            for c in r["candidates"]:
                if c["incumbent"] and last_name(c["name"]) not in holders:
                    self.warnings.append(
                        f"{r['race_id']}: {c['name']} flagged incumbent but "
                        "not a current holder of this seat per legislators"
                    )

    # ----- other sections --------------------------------------------------
    def _history(self, rows: list[dict], special: bool) -> list[dict[str, Any]]:
        by_year: dict[tuple[int, bool], list[dict]] = defaultdict(list)
        for h in rows:
            by_year[(h["year"], h.get("special", False))].append(h)
        out = []
        for year, sp in sorted(by_year, reverse=True)[:HISTORY_CYCLES]:
            group = by_year[(year, sp)]
            total = max((g.get("total_votes") or 0) for g in group) or None
            cands = [
                {
                    "name": g["candidate_name"],
                    "party_label": g["party_label"],
                    "votes": g.get("votes"),
                    "pct": _pct(g.get("votes"), total),
                    "writein": g.get("writein", False),
                }
                for g in sorted(group, key=lambda g: -(g.get("votes") or 0))
            ]
            out.append(
                {
                    "year": year,
                    "special": sp,
                    "total_votes": total,
                    "candidates": cands,
                    "source_ids": sorted({sid for g in group for sid in g["source_ids"]}),
                }
            )
        return out

    def _demographics(
        self, office: str, po: str, district: int | None, demo_by_seat: dict, boundary_sets: dict
    ) -> dict[str, Any] | None:
        if office != "house":
            return None
        rows = demo_by_seat.get((po, district), [])
        if not rows:
            return {
                "available": False,
                "reason": "boundaries_changed" if po in self._changed_states() else "no_data",
                "rows": [],
            }
        return {
            "available": True,
            "vintage": "ACS 5-year 2020-2024",
            "rows": [
                {
                    "label": r["label"],
                    "variable": r["variable"],
                    "estimate": r["estimate"],
                    "moe": r["margin_of_error"],
                    "source_ids": r["source_ids"],
                }
                for r in rows
            ],
        }

    def _changed_states(self) -> set[str]:
        import yaml

        p = self.repo_root / "data" / "seeds" / "boundary-sets-2026.yaml"
        return set(yaml.safe_load(p.read_text(encoding="utf-8")).get("changed_for_2026", {}))

    def _used_source_ids(self, races: list[dict], offices: dict, boundary_sets: dict) -> set[str]:
        used: set[str] = set()

        def walk(o: Any) -> None:
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "source_ids":
                        used.update(v)
                    else:
                        walk(v)
            elif isinstance(o, list):
                for x in o:
                    walk(x)

        walk(races)
        walk(list(offices.values()))
        walk(list(boundary_sets.values()))
        return used

    # ----- output ----------------------------------------------------------
    def _write(
        self,
        races,
        candidates_flat,
        offices,
        sources,
        status,
        finance,
        history,
        demographics,
        boundary_sets,
    ) -> dict[str, Any]:
        out = self.out_dir
        if out.exists():
            shutil.rmtree(out)
        (out / "races").mkdir(parents=True)
        for r in races:
            write_json(out / "races" / f"{r['race_id']}.json", r)
        index = [
            {
                k: r[k]
                for k in ("race_id", "office", "state_po", "state_name", "district", "special")
            }
            | {
                "candidate_count": len(r["candidates"]),
                "list_status": r["candidate_list"]["status"],
            }
            for r in races
        ]
        write_json(out / "races.json", index)

        states = []
        for st in STATES:
            o = offices.get(st.po)
            states.append(
                {
                    "state_po": st.po,
                    "state_name": st.name,
                    "state_fips": st.fips,
                    "house_seats": st.house_seats,
                    "office": o,
                    "race_ids": [r["race_id"] for r in races if r["state_po"] == st.po],
                    "boundary_set": boundary_sets.get(st.po),
                }
            )
        write_json(out / "states.json", states)
        write_json(out / "sources.json", sorted(sources.values(), key=lambda s: s["source_id"]))
        meta = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": self.now.isoformat(),
            "live_enabled": self.live_enabled,
            "status": status,
            "warnings": self.warnings,
        }
        write_json(out / "meta.json", meta)

        bdir = self.in_dir / "boundaries"
        if bdir.exists():
            for sub in ("display", "lookup"):
                if (bdir / sub).exists():
                    shutil.copytree(bdir / sub, out / "boundaries" / sub)
            if (bdir / "states.geojson").exists():
                shutil.copy(bdir / "states.geojson", out / "boundaries" / "states.geojson")

        dl = out / "downloads"
        datasets = {
            "candidates": (
                candidates_flat,
                "Candidates on the 2026 general election ballot, "
                "from official state lists, with FEC fallback where noted.",
            ),
            "fec-finance": (finance, "FEC financial summary for 2026 House and Senate candidates."),
            "history": (history, "Historical general election results, 2006 onward."),
            "demographics": (
                demographics,
                "ACS 5-year estimates by congressional district (119th Congress boundaries).",
            ),
            "state-election-offices": (
                list(offices.values()),
                "Official state election office links.",
            ),
            "boundary-sets": (
                list(boundary_sets.values()),
                "District boundary sets for the 2026 election with enacting instruments.",
            ),
            "sources": (
                sorted(sources.values(), key=lambda s: s["source_id"]),
                "Every source cited on the site.",
            ),
        }
        manifest = []
        for name, (rows, desc) in datasets.items():
            write_json(dl / f"{name}.json", rows)
            write_csv(dl / f"{name}.csv", rows)
            sids = sorted({sid for r in rows for sid in r.get("source_ids", [])})
            if name == "sources":
                sids = []
            manifest.append(
                {
                    "name": name,
                    "description": desc,
                    "rows": len(rows),
                    "files": [f"{name}.csv", f"{name}.json"],
                    "source_ids": sids,
                    "license": "CC BY 4.0 for compilation; underlying source "
                    "licenses apply (see source_ids)",
                }
            )
        write_json(dl / "index.json", manifest)
        return meta


def _office(o: str):
    from .core.models import Office

    return Office(o)


def _first_compatible(a: str, b: str) -> bool:
    if not a or not b:
        return True
    return a == b or a[0] == b[0] and (len(a) == 1 or len(b) == 1)


def _finance(f: dict | None) -> dict[str, Any] | None:
    if not f or f.get("receipts") is None:
        return None
    return {
        k: f.get(k)
        for k in ("receipts", "disbursements", "cash_on_hand", "coverage_end_date", "source_ids")
    }
