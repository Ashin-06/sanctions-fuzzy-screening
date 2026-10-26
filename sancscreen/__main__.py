"""
CLI entrypoint for `sancscreen`.

Usage:
  python -m sancscreen bench
  python -m sancscreen serve                     # settings: SANCSCREEN_* environment variables
  python -m sancscreen migrate                   # apply database migrations and exit
  python -m sancscreen screen --name "विक्टर बुट" --country RU --dob 1967-01-13
  python -m sancscreen realdata --sdn SDN.XML     # the real OFAC list -> results/real_data.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from sancscreen.bench import (
    SanctionsScreeningPipeline,
    format_benchmark_report,
    run_benchmark,
)
from sancscreen.matcher import ScreeningQuery


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        prog="sancscreen",
        description="Cross-Script Phonetic, Transliteration & UBO Graph Sanctions Screening Engine",
    )
    sub = parser.add_subparsers(dest="command")

    # bench subcommand
    bench_p = sub.add_parser("bench", help="Run the 300-wire benchmark suite")
    bench_p.add_argument("--json", action="store_true", help="Output raw JSON benchmark metrics")

    # serve subcommand
    serve_p = sub.add_parser("serve", help="Start the FastAPI server and interactive web console")
    serve_p.add_argument("--host", help="Bind host (default SANCSCREEN_HOST or 127.0.0.1; others need API keys)")
    serve_p.add_argument("--port", type=int, help="Bind port (default SANCSCREEN_PORT or 8016)")
    sub.add_parser("migrate", help="Apply database migrations to SANCSCREEN_DATABASE_URL")

    # screen subcommand
    screen_p = sub.add_parser("screen", help="Screen a single wire transfer party")
    screen_p.add_argument("--name", required=True, help="Party or entity name (any script)")
    screen_p.add_argument("--dob", default=None, help="Date of Birth (YYYY-MM-DD)")
    screen_p.add_argument("--country", default=None, help="ISO-2 Country code")
    screen_p.add_argument("--id", dest="identifier", default=None, help="Passport / BIC / LEI")

    real_p = sub.add_parser("realdata", help="Screen against the real OFAC SDN list -> results/real_data.json")
    real_p.add_argument("--sdn", required=True, help="Path to OFAC's SDN.XML")
    real_p.add_argument("--sample", type=int, default=30, help="Wires to re-screen with a full scan")
    real_p.add_argument("--out", default="results/real_data.json")
    real_p.add_argument("--wikidata", default=None,
                        help="Folder of Wikidata name CSVs (see realdata.py): also run the held-out set -> heldout.json")

    args = parser.parse_args(argv)

    if args.command == "realdata":
        from sancscreen.realdata import main as realdata

        res = realdata(args.sdn, args.out, args.sample, args.wikidata)
        if "heldout" in res:
            res["heldout"] = res["heldout"]["by_split"]
        print(json.dumps({k: v for k, v in res.items() if "examples" not in k}, indent=2, ensure_ascii=False))
        return 0

    if args.command in ("serve", "migrate"):
        from sancscreen import db, ops

        for name, val in (("HOST", getattr(args, "host", None)), ("PORT", getattr(args, "port", None))):
            if val is not None:
                os.environ[f"SANCSCREEN_{name}"] = str(val)
        try:
            settings = ops.load_settings()  # fail here, before uvicorn, with a readable message
        except ops.ConfigError as e:
            print(f"configuration error: {e}", file=sys.stderr)
            return 2
        if args.command == "migrate":
            print(*(db.migrate(db.engine(settings.database_url)) or ["up to date"]), sep="\n")
            return 0
        import uvicorn

        ops.setup_logging(settings.log_level)
        try:
            uvicorn.run("sancscreen.api:app", host=settings.host, port=settings.port, log_config=None, access_log=False)
        except ops.ConfigError as e:  # raised while importing the app, e.g. no SANCSCREEN_SDN_XML in production
            print(f"configuration error: {e}", file=sys.stderr)
            return 2
        return 0

    if args.command == "screen":
        pipeline = SanctionsScreeningPipeline()
        res = pipeline.screen_wire(
            ScreeningQuery(
                query_id="CLI-001",
                name=args.name,
                dob=args.dob,
                country=args.country,
                identifier=args.identifier,
            )
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    # Default or "bench": run benchmark
    res = run_benchmark()
    if getattr(args, "json", False):
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(format_benchmark_report(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
