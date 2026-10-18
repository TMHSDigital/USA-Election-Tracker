"""Command line entry point.

  uv run ingest run [ADAPTER ...] --out ../.data/raw
  uv run ingest compose --in ../.data/raw --out ../site/public/data
  uv run ingest check-seeds
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .adapters import ADAPTERS
from .compose import Composer
from .core.adapter import Context, run_adapters
from .core.http import LiveHttp

REPO_ROOT = Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ingest")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run adapters; failures keep last good data")
    r.add_argument("adapters", nargs="*", help=f"subset of: {', '.join(ADAPTERS)}")
    r.add_argument("--out", type=Path, default=REPO_ROOT / ".data" / "raw")
    r.add_argument("--strict", action="store_true", help="exit 1 if any adapter failed")

    c = sub.add_parser("compose", help="build the site data bundle")
    c.add_argument("--in", dest="in_dir", type=Path, default=REPO_ROOT / ".data" / "raw")
    c.add_argument("--out", type=Path, default=REPO_ROOT / ".data" / "site")

    sub.add_parser("check-seeds", help="validate curated seed files (used in CI)")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.cmd == "run":
        names = args.adapters or [n for n, a in ADAPTERS.items() if not a.experimental]
        unknown = [n for n in names if n not in ADAPTERS]
        if unknown:
            p.error(f"unknown adapters: {unknown}")
        ctx = Context(http=LiveHttp(), repo_root=REPO_ROOT, out_dir=args.out)
        status = run_adapters([ADAPTERS[n](ctx) for n in names], args.out)
        failed = [k for k in names if not status["adapters"][k]["ok"]]
        summary = {"failed": failed, "ok": [k for k in names if k not in failed]}
        (args.out / "last-run.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary))
        return 1 if (failed and args.strict) else 0

    if args.cmd == "compose":
        live = os.environ.get("LIVE_RESULTS_ENABLED", "false").lower() == "true"
        meta = Composer(args.in_dir, args.out, REPO_ROOT, live_enabled=live).run()
        for w in meta["warnings"]:
            print(f"WARNING: {w}")
        return 0

    if args.cmd == "check-seeds":
        import tempfile

        from .core.http import FixtureHttp

        with tempfile.TemporaryDirectory() as tmp:
            ctx = Context(http=FixtureHttp(Path(tmp), {}), repo_root=REPO_ROOT,
                          out_dir=Path(tmp))
            names = ["state_offices", "candidates_official"]
            status = run_adapters([ADAPTERS[n](ctx) for n in names], Path(tmp))
            bad = {k: v["error"] for k, v in status["adapters"].items() if not v["ok"]}
        if bad:
            for k, v in bad.items():
                print(f"{k}: {v}", file=sys.stderr)
            return 1
        print("seeds ok")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
