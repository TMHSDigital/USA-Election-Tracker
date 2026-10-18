"""Adapters for curated, human-reviewed seed files in data/seeds.

Seeds are the source of truth for things no national API provides: official
general-election candidate lists and state election office URLs. Every row
cites the official page it came from.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from ..core.adapter import Adapter, Dataset, ValidationFailed
from ..core.models import Office, SeedCandidate, SeedCoverage, SourceRecord, StateOffice
from ..core.registry import load_registry, source_record
from ..core.states import BY_PO
from ..core.util import parse_bool, parse_date, race_id, to_datetime, url_source_id

SEED_LICENSE = "Government publication, cited and linked; see publisher terms"
OFFICE_MAP = {"us house": Office.HOUSE, "us senate": Office.SENATE, "governor": Office.GOVERNOR}


class StateOfficesAdapter(Adapter):
    id = "state_offices"
    description = "Official state election office URLs (curated seed)"

    def fetch(self) -> dict[str, Any]:
        path = self.ctx.repo_root / "data" / "seeds" / "state-election-offices.yaml"
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def validate(self, raw: dict[str, Any]) -> dict[str, Any]:
        states = raw.get("states") or []
        seen = Counter(s["state_po"] for s in states)
        dupes = [k for k, v in seen.items() if v > 1]
        if dupes:
            raise ValidationFailed(f"duplicate states in office seed: {dupes}")
        missing = sorted(set(BY_PO) - set(seen))
        if missing:
            raise ValidationFailed(f"office seed missing states: {missing}")
        for s in states:
            for key in ("homepage_url", "voter_info_url", "results_url"):
                url = s.get(key)
                if url and not str(url).startswith("https://") and not str(url).startswith(
                    "http://"
                ):
                    raise ValidationFailed(f"{s['state_po']}.{key} is not a URL: {url}")
        return raw

    def normalize(self, raw: dict[str, Any]) -> Dataset:
        rows: list[StateOffice] = []
        sources: dict[str, SourceRecord] = {}
        for s in raw["states"]:
            po = s["state_po"]
            retrieved = to_datetime(s.get("retrieved_at") or raw["retrieved_at"])
            url = s.get("homepage_url") or s.get("voter_info_url") or s.get("results_url")
            sid = f"state-office:{po.lower()}"
            sources[sid] = SourceRecord(
                source_id=sid,
                name=f"{s['office_name']} website",
                publisher=s["office_name"],
                url=url,
                license=SEED_LICENSE,
                retrieved_at=retrieved,
                notes="Links verified by the project's weekly link check.",
            )
            rows.append(
                StateOffice(
                    state_po=po,
                    state_name=s["state_name"],
                    state_fips=str(s["state_fips"]).zfill(2),
                    office_name=s["office_name"],
                    homepage_url=s.get("homepage_url"),
                    voter_info_url=s.get("voter_info_url"),
                    results_url=s.get("results_url"),
                    results_platform=s.get("results_platform"),
                    general_election_date=parse_date(str(s["general_election_date"])),
                    notes=str(s.get("notes") or ""),
                    source_ids=[sid],
                )
            )
        rows.sort(key=lambda r: r.state_name)
        return Dataset(
            tables={"state_offices": rows},
            sources=list(sources.values()),
            retrieved_at=to_datetime(raw["retrieved_at"]),
        )


class OfficialCandidatesAdapter(Adapter):
    id = "candidates_official"
    description = "Candidates from official state certified general election lists (curated seed)"

    def fetch(self) -> list[tuple[str, dict[str, str]]]:
        seeds = self.ctx.repo_root / "data" / "seeds"
        files: list[Path] = []
        gov = seeds / "governors-2026.csv"
        if gov.exists():
            files.append(gov)
        fed_dir = seeds / "federal-candidates-2026"
        if fed_dir.exists():
            files.extend(sorted(fed_dir.glob("*.csv")))
        rows: list[tuple[str, dict[str, str]]] = []
        for f in files:
            with f.open(encoding="utf-8-sig", newline="") as fh:
                for r in csv.DictReader(fh):
                    rows.append((f.name, {k.strip(): (v or "").strip() for k, v in r.items() if k}))
        if not rows:
            raise ValidationFailed("no candidate seed rows found")
        return rows

    def normalize(self, raw: list[tuple[str, dict[str, str]]]) -> Dataset:
        registry = load_registry(self.ctx.repo_root)
        seeds_src = source_record(registry, "project_seeds", retrieved_at=self.ctx.now)
        sources: dict[str, SourceRecord] = {seeds_src.source_id: seeds_src}
        candidates: list[SeedCandidate] = []
        coverage: dict[tuple[str, Office], SeedCoverage] = {}
        errors: list[str] = []

        for fname, r in raw:
            try:
                po = r["state_po"].upper()
                if po not in BY_PO:
                    raise ValueError(f"unknown state {po}")
                office = OFFICE_MAP[r["office"].strip().lower()]
                special = parse_bool(r.get("special"))
                district: int | None = None
                # "List not found" marker rows carry no candidate and may omit district.
                if office == Office.HOUSE and r.get("candidate_name"):
                    district = int(r["district"])
                    seats = BY_PO[po].house_seats
                    if seats == 1 and district not in (0, 1):
                        raise ValueError(f"{po} is at-large but district={district}")
                    if seats == 1:
                        district = 0
                    elif not 1 <= district <= seats:
                        raise ValueError(f"{po} district {district} outside 1..{seats}")
                url = r.get("source_url", "")
                retrieved = to_datetime(r.get("retrieved_at") or self.ctx.now)
                if not url.startswith("http"):
                    raise ValueError("missing source_url")
                sid = url_source_id("state-list", url)
                if sid not in sources:
                    sources[sid] = SourceRecord(
                        source_id=sid,
                        name=r.get("source_title") or f"{BY_PO[po].name} official candidate list",
                        publisher=f"{BY_PO[po].name} state election officials",
                        url=url,
                        license=SEED_LICENSE,
                        retrieved_at=retrieved,
                    )
                name = r.get("candidate_name", "")
                notes = r.get("notes", "")
                key = (po, office)
                if not name:
                    if key not in coverage or coverage[key].status != "official":
                        coverage[key] = SeedCoverage(state_po=po, office=office,
                                                     status="not_found", list_url=url,
                                                     notes=notes, source_ids=[sid])
                    continue
                coverage[key] = SeedCoverage(state_po=po, office=office, status="official",
                                             list_url=url, source_ids=[sid])
                order = r.get("ballot_order", "")
                candidates.append(
                    SeedCandidate(
                        race_id=race_id(2026, office, po, district, special),
                        state_po=po,
                        office=office,
                        district=district,
                        special=special,
                        name=name,
                        ballot_name=r.get("ballot_name") or name,
                        party_label=r.get("party_ballot_label", ""),
                        incumbent=parse_bool(r.get("incumbent")),
                        ballot_order=int(order) if order else None,
                        write_in="write-in" in notes.lower(),
                        running_mate=r.get("running_mate") or None,
                        fec_candidate_id=(r.get("fec_candidate_id") or None),
                        notes=notes,
                        source_ids=[sid],
                    )
                )
            except (KeyError, ValueError) as e:
                errors.append(f"{fname}: {e}: {r}")
        if errors:
            raise ValidationFailed("candidate seed errors:\n" + "\n".join(errors[:50]))

        dup = Counter((c.race_id, c.name.lower()) for c in candidates)
        dupes = [k for k, v in dup.items() if v > 1]
        if dupes:
            raise ValidationFailed(f"duplicate candidates in seeds: {dupes[:10]}")

        candidates.sort(key=lambda c: (c.race_id, c.name))
        return Dataset(
            tables={
                "seed_candidates": candidates,
                "seed_coverage": sorted(coverage.values(), key=lambda c: (c.state_po, c.office)),
            },
            sources=list(sources.values()),
            retrieved_at=self.ctx.now,
        )
